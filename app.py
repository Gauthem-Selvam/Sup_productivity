from flask import (
    Flask, render_template, request,
    redirect, url_for, session, jsonify
)
import pandas as pd
import os
import smtplib
from email.message import EmailMessage

app = Flask(__name__)
app.secret_key = "super_secret_key"

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

USERNAME = "admin"
PASSWORD = "huddle123"


# ======================
# LOGIN ROUTES
# ======================

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if (
            request.form["username"] == USERNAME
            and request.form["password"] == PASSWORD
        ):
            session["user"] = USERNAME
            return redirect(url_for("upload"))
        return "Invalid credentials"
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ======================
# UPLOAD PAGE
# ======================

@app.route("/", methods=["GET"])
def upload():
    if "user" not in session:
        return redirect(url_for("login"))
    return render_template("upload.html")


# ======================
# PROCESS FILE
# ======================

@app.route("/process", methods=["POST"])
def process_file():
    try:
        file = request.files.get("file")

        if not file or file.filename == "":
            return jsonify({"status": "error",
                            "message":
                            "No file uploaded"}), 400

        file.stream.seek(0)
        df = pd.read_csv(file)

        if df.empty:
            return jsonify({"status": "error", "message":
                            "Uploaded file is empty"}), 400

        # Normalize column names
        df.columns = df.columns.str.strip()

        required_cols = {
            "Supervisor", "Case Owner", "Month", "Productivity %"
        }
        missing = required_cols - set(df.columns)
        if missing:
            return jsonify({
                "status": "error",
                "message": f"Missing columns: {', '.join(missing)}"
            }), 400

        # Ensure numeric
        df["Productivity %"] = pd.to_numeric(
            df["Productivity %"],
            errors="coerce")

        # ======================
        # METRICS (CORRECT)
        # ======================

        total_supervisors = df["Supervisor"].nunique()
        total_case_owners = df["Case Owner"].nunique()
        avg_productivity = df["Productivity %"].mean()

        # ======================
        # SUPERVISOR SUMMARY
        # ======================

        supervisor_summary = (
            df.groupby("Supervisor")
              .agg(
                  case_owners=("Case Owner", "nunique"),
                  months_reported=("Month", "count"),
                  avg_productivity=("Productivity %", "mean")
              )
            .reset_index()
        )

        supervisor_table_html = supervisor_summary.to_html(
            index=False, border=1)

        # ======================
        # CASE OWNER SUMMARY
        # ======================

        case_owner_summary = (
            df.groupby(["Supervisor", "Case Owner"])
              .agg(
                  months_reported=("Month", "count"),
                  avg_productivity=("Productivity %", "mean")
              )
            .reset_index()
        )

        top_table_html = case_owner_summary.to_html(
            index=False, border=1)

        # ======================
        # TOP 5 CASE OWNERS
        # ======================

        top_df = (
            case_owner_summary
            .sort_values(by="avg_productivity", ascending=False)
            .head(5)
        )

        top_table_html = top_df.to_html(index=False, border=1)

        # ======================
        # SEND EMAIL
        # ======================

        send_huddle_email(
            df=df,
            total_supervisors=total_supervisors,
            total_case_owners=total_case_owners,
            avg_productivity=avg_productivity,
            top_table_html=top_table_html,
            supervisor_table_html=supervisor_table_html,
        )

        return jsonify({"status": "success"})

    except Exception as e:
        print("❌ Processing error:", str(e))
        return jsonify({"status": "error", "message": str(e)}), 500


# ======================
# EMAIL FUNCTION
# ======================

def send_huddle_email(
    df,
    total_supervisors,
    total_case_owners,
    avg_productivity,
    top_table_html,
    supervisor_table_html,
):
    EMAIL_USER = os.getenv("EMAIL_USER")
    EMAIL_PASS = os.getenv("EMAIL_PASS")

    if not EMAIL_USER or not EMAIL_PASS:
        raise RuntimeError("Email credentials missing")

    report_month = df["Month"].iloc[0]

    msg = EmailMessage()
    msg["Subject"] = f"📊 Huddle Productivity Report – {report_month}"
    msg["From"] = EMAIL_USER
    msg["To"] = "," .join([
        "gauthem.selvam@ironmountain.com",
        "nazeen.nazeen@ironmountain.com"
    ])

    msg.set_content("Your email client does not support HTML.")
    msg.add_alternative(f"""
    <html>
    <body style="font-family: Arial, sans-serif;">
        <h2>📊 Huddle Productivity Summary – {report_month}</h2>

        <ul>
            <li><b>Total Supervisors:</b> {total_supervisors}</li>
            <li><b>Total Case Owners:</b> {total_case_owners}</li>
            <li><b>Average Productivity:</b> {avg_productivity:.2f}%</li>
        </ul>

        <h3>👥 Supervisor Summary</h3>
        {supervisor_table_html}

        <h3>🏆 Top 5 Case Owners (Yearly)</h3>
        {top_table_html}

        <p>Regards,<br><b>Huddle Automation</b></p>
    </body>
    </html>
    """, subtype="html")

    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=60) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASS)
            server.send_message(msg)

        print("📧 Email sent successfully")

    except Exception as e:
        print("❌ Email sending failed:", str(e))
        raise


# ======================
# APP START
# ======================

if __name__ == "__main__":
    print("🚀 Starting Huddle App...")
    app.run(host="127.0.0.1", port=5001, debug=True)
