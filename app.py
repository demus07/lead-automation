"""Lead automation — one small app. Run: python app.py, then open http://localhost:5050"""
import os
import threading

from dotenv import load_dotenv

load_dotenv()

from flask import Flask, flash, redirect, render_template, request, url_for  # noqa: E402

from leads import db, discover, draft, pipeline, send  # noqa: E402

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "local-only")


@app.context_processor
def globals_():
    return {"state": pipeline.state, "stages": db.STAGES, "pending_count": len(db.pending_messages())}


def back(default="dashboard", **kw):
    return redirect(request.referrer or url_for(default, **kw))


# ---------------------------------------------------------------- dashboard
@app.get("/")
def dashboard():
    return render_template("dashboard.html", counts=db.status_counts(), queue=db.pending_messages(),
                           follow_ups=db.follow_ups_due(), sent_today=db.sent_today(), settings=db.settings(),
                           smtp_ok=send.configured(), llm_ok=draft.llm_configured())


@app.post("/run")
def run():
    pipeline.run_in_background(discover_new=request.form.get("discover") != "no")
    flash("Run started — refresh in a minute.")
    return back()


# ---------------------------------------------------------------- approvals
@app.post("/message/<int:msg_id>/approve")
def approve(msg_id):
    err = pipeline.approve(msg_id, request.form.get("subject", ""), request.form["body"])
    flash(err or "Sent.")
    return back()


@app.post("/message/<int:msg_id>/reject")
def reject(msg_id):
    pipeline.reject(msg_id)
    return back()


@app.post("/lead/<int:lead_id>/redraft")
def redraft(lead_id):
    pipeline.redraft(lead_id)
    return back()


# ---------------------------------------------------------------- leads / CRM
@app.get("/leads")
def leads():
    status = request.args.get("status")
    return render_template("leads.html", leads=db.list_leads(status), status=status, counts=db.status_counts())


@app.post("/leads/add")
def add_leads():
    n = discover.add_manual(request.form["urls"])
    flash(f"Added {n} lead(s). They'll be researched on the next run.")
    if n and request.form.get("process"):
        pipeline.run_in_background(discover_new=False)
    return back("leads")


@app.get("/lead/<int:lead_id>")
def lead(lead_id):
    item = db.get_lead(lead_id)
    if not item:
        return redirect(url_for("leads"))
    return render_template("lead.html", lead=item, messages=db.messages_for(lead_id), notes=db.notes_for(lead_id))


@app.post("/lead/<int:lead_id>/update")
def update_lead(lead_id):
    fields = {"status": request.form["status"], "follow_up": request.form.get("follow_up") or None}
    db.update_lead(lead_id, **fields)
    return back()


@app.post("/lead/<int:lead_id>/note")
def add_note(lead_id):
    if request.form["body"].strip():
        db.add_note(lead_id, request.form["body"].strip())
    return back()


@app.post("/lead/<int:lead_id>/research")
def research_again(lead_id):
    db.update_lead(lead_id, status="new")
    db.reject_pending(lead_id)
    threading.Thread(target=pipeline.process, args=(lead_id,), daemon=True).start()
    flash("Researching again — refresh in a moment.")
    return back()


@app.post("/lead/<int:lead_id>/block")
def block_lead(lead_id):
    item = db.get_lead(lead_id)
    db.block(item["domain"])
    db.update_lead(lead_id, status="lost", note="Do not contact")
    db.reject_pending(lead_id)
    flash(f"{item['domain']} won't be contacted again.")
    return back()


@app.post("/lead/<int:lead_id>/delete")
def delete_lead(lead_id):
    db.delete_lead(lead_id)
    return redirect(url_for("leads"))


# ---------------------------------------------------------------- settings
@app.route("/settings", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        db.save_settings(request.form.to_dict())
        flash("Saved.")
        return redirect(url_for("settings"))
    return render_template("settings.html", s=db.settings(), blocked=db.blocked(), categories=discover.CATEGORIES,
                           smtp_ok=send.configured(), llm_ok=draft.llm_configured(),
                           llm_model=os.getenv("LLM_MODEL"))


@app.post("/block")
def block():
    if request.form["value"].strip():
        db.block(request.form["value"])
    return back("settings")


@app.post("/unblock")
def unblock():
    db.unblock(request.form["value"])
    return back("settings")


db.init()
if __name__ == "__main__":
    threading.Thread(target=pipeline.scheduler, daemon=True).start()
    app.run(port=int(os.getenv("PORT", 5050)), debug=False)
