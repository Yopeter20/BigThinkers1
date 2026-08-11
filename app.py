import os
import random
import uuid
from datetime import datetime, timedelta
from functools import wraps

from flask import (Flask, render_template, redirect, url_for, request,
                    flash, abort, jsonify, send_from_directory, session)
from flask_login import (LoginManager, login_user, logout_user, login_required,
                          current_user)
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

from models import (db, User, Update, Post, Comment, Reaction, Message,
                     ADMIN_POSITIONS, BADGE_ICONS, MEMBERSHIP_PLANS, PLAN_RANK)
from mail import send_reset_code_email

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads", "profile_pictures")
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
MAX_UPLOAD_SIZE = 4 * 1024 * 1024  # 4 MB

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(BASE_DIR, "instance", "database.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAIN_ADMIN_EMAIL"] = os.environ.get("MAIN_ADMIN_EMAIL", "nkakapeter@gmail.com")
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_SIZE

db.init_app(app)

login_manager = LoginManager()
login_manager.login_view = "signin"
login_manager.init_app(app)

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, "instance"), exist_ok=True)


# ---------------------------------------------------------
# Country codes (Section 13)
# ---------------------------------------------------------
COUNTRY_CODES = sorted([
    ("Zambia", "+260"), ("South Africa", "+27"), ("Zimbabwe", "+263"),
    ("Malawi", "+265"), ("Tanzania", "+255"), ("Kenya", "+254"),
    ("Uganda", "+256"), ("Nigeria", "+234"), ("Ghana", "+233"),
    ("Egypt", "+20"), ("Ethiopia", "+251"), ("United States", "+1"),
    ("Canada", "+1"), ("United Kingdom", "+44"), ("France", "+33"),
    ("Germany", "+49"), ("Botswana", "+267"), ("Namibia", "+264"),
    ("Mozambique", "+258"), ("Rwanda", "+250"), ("India", "+91"),
    ("China", "+86"), ("Australia", "+61"), ("Brazil", "+55"),
    ("United Arab Emirates", "+971"),
], key=lambda x: x[0])


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin():
            abort(403)
        return f(*args, **kwargs)
    return wrapper


def account_active_required(f):
    """Blocks blocked/frozen accounts from using the app."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if current_user.is_authenticated:
            if current_user.account_status == "blocked":
                logout_user()
                flash("Your account has been blocked. Contact an administrator.", "danger")
                return redirect(url_for("signin"))
        return f(*args, **kwargs)
    return wrapper


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def generate_reset_code():
    return f"{random.randint(0, 999999):06d}"


def time_greeting():
    hour = datetime.now().hour
    if hour < 12:
        return "Good Morning"
    elif hour < 18:
        return "Good Afternoon"
    else:
        return "Good Evening"


def profile_pic_url(user):
    if user.profile_picture:
        return url_for("uploaded_profile_picture", filename=user.profile_picture)
    return url_for("static", filename="img/avatar-placeholder.svg")


@app.context_processor
def inject_globals():
    unread_message_count = 0
    if current_user.is_authenticated:
        unread_message_count = Message.query.filter_by(
            recipient_id=current_user.id, read=False
        ).count()
    return dict(
        current_user=current_user,
        badge_icons=BADGE_ICONS,
        membership_plans=MEMBERSHIP_PLANS,
        profile_pic_url=profile_pic_url,
        unread_message_count=unread_message_count,
    )


@app.route("/uploads/profile_pictures/<path:filename>")
def uploaded_profile_picture(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


@app.route("/sw.js")
def service_worker():
    # Served from the root (not /static/) so its default scope covers the
    # whole app rather than just /static/ — required for TWA/PWA installs.
    response = send_from_directory(
        os.path.join(app.static_folder), "sw.js"
    )
    response.headers["Service-Worker-Allowed"] = "/"
    response.headers["Cache-Control"] = "no-cache"
    return response


# ---------------------------------------------------------
# Public pages
# ---------------------------------------------------------
@app.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    return render_template("index.html")


# ---------------------------------------------------------
# Auth: Signup / Signin / Logout
# ---------------------------------------------------------
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        first_name = request.form.get("first_name", "").strip()
        surname = request.form.get("surname", "").strip()
        email = request.form.get("email", "").strip().lower()
        country_code = request.form.get("country_code", "+260")
        phone_number = request.form.get("phone_number", "").strip()
        plan = request.form.get("membership_plan", "BASIC").upper()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        terms = request.form.get("terms")

        errors = []
        if not first_name or not surname or not email or not password:
            errors.append("Please fill in all required fields.")
        if plan not in MEMBERSHIP_PLANS:
            plan = "BASIC"
        if password != confirm_password:
            errors.append("Passwords do not match.")
        if len(password) < 6:
            errors.append("Password must be at least 6 characters long.")
        if not terms:
            errors.append("You must accept the Terms and Conditions.")
        if User.query.filter_by(email=email).first():
            errors.append("An account with this email already exists.")

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("signup.html", country_codes=COUNTRY_CODES, form=request.form)

        user = User(
            first_name=first_name,
            surname=surname,
            email=email,
            phone_country_code=country_code,
            phone_number=phone_number,
            membership_plan=plan,
        )
        user.set_password(password)

        # Main admin account is auto-approved and promoted
        if email == app.config["MAIN_ADMIN_EMAIL"].lower():
            user.role = "admin"
            user.position = "Super Administrator"
            user.subscription_status = "active"
            user.approved_at = datetime.utcnow()

        db.session.add(user)
        db.session.commit()

        flash("Account created successfully! Please sign in.", "success")
        return redirect(url_for("signin"))

    return render_template("signup.html", country_codes=COUNTRY_CODES, form={})


@app.route("/signin", methods=["GET", "POST"])
def signin():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        remember = bool(request.form.get("remember"))

        user = User.query.filter_by(email=email).first()

        if not user or not user.check_password(password):
            flash("Incorrect email or password.", "danger")
            return render_template("signin.html")

        if user.account_status == "blocked":
            flash("This account has been blocked. Please contact an administrator.", "danger")
            return render_template("signin.html")

        login_user(user, remember=remember)
        flash(f"Welcome back, {user.first_name}!", "success")
        return redirect(url_for("dashboard"))

    return render_template("signin.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("index"))


# ---------------------------------------------------------
# Forgot password (emailed 6-digit code, sent from
# bigthinkersorganization@gmail.com)
# ---------------------------------------------------------
@app.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = User.query.filter_by(email=email).first()

        if user:
            code = generate_reset_code()
            user.reset_code = code
            user.reset_code_expires = datetime.utcnow() + timedelta(minutes=10)
            db.session.commit()

            sent = send_reset_code_email(user.email, user.first_name, code)

            session["reset_email"] = user.email
            session.pop("reset_verified", None)

            if sent:
                flash("A 6-digit reset code has been sent to your email.", "success")
            else:
                flash("We couldn't send the email right now. Please try again shortly "
                      "or contact an administrator.", "danger")
            return redirect(url_for("verify_code"))

        # Don't reveal whether the email exists.
        flash("If this email exists, a reset code has been sent.", "info")
        return redirect(url_for("signin"))

    return render_template("forgot_password.html")


@app.route("/verify_code", methods=["GET", "POST"])
def verify_code():
    email = session.get("reset_email")
    if not email:
        flash("Please request a reset code first.", "danger")
        return redirect(url_for("forgot_password"))

    if request.method == "POST":
        code = request.form.get("code", "").strip()
        user = User.query.filter_by(email=email).first()

        if not user or not user.reset_code or not user.reset_code_expires:
            flash("Invalid or expired code. Please request a new one.", "danger")
            return redirect(url_for("forgot_password"))

        if datetime.utcnow() > user.reset_code_expires:
            flash("This code has expired. Please request a new one.", "danger")
            return redirect(url_for("forgot_password"))

        if code != user.reset_code:
            flash("Incorrect code. Please try again.", "danger")
            return render_template("verify_code.html", email=email)

        session["reset_verified"] = True
        flash("Code verified. You can now set a new password.", "success")
        return redirect(url_for("reset_password"))

    return render_template("verify_code.html", email=email)


@app.route("/reset_password", methods=["GET", "POST"])
def reset_password():
    email = session.get("reset_email")
    if not email or not session.get("reset_verified"):
        flash("Please verify your reset code first.", "danger")
        return redirect(url_for("forgot_password"))

    if request.method == "POST":
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if len(new_password) < 6:
            flash("Password must be at least 6 characters long.", "danger")
        elif new_password != confirm_password:
            flash("Passwords do not match.", "danger")
        else:
            user = User.query.filter_by(email=email).first()
            if not user:
                flash("Something went wrong. Please request a new code.", "danger")
                return redirect(url_for("forgot_password"))

            user.set_password(new_password)
            user.reset_code = None
            user.reset_code_expires = None
            user.force_password_change = False
            db.session.commit()

            session.pop("reset_email", None)
            session.pop("reset_verified", None)

            flash("Password reset successfully. Please sign in.", "success")
            return redirect(url_for("signin"))

    return render_template("reset_password.html")


# ---------------------------------------------------------
# Dashboard
# ---------------------------------------------------------
@app.route("/dashboard")
@login_required
@account_active_required
def dashboard():
    updates = Update.query.filter_by(published=True).order_by(Update.created_at.desc()).all()
    visible_updates = [u for u in updates if u.visible_to(current_user.membership_plan)][:5]
    recent_posts = Post.query.order_by(Post.created_at.desc()).limit(5).all()

    stats = dict(
        total_members=User.query.count(),
        total_updates=Update.query.count(),
        total_posts=Post.query.count(),
    )

    return render_template(
        "dashboard.html",
        greeting=time_greeting(),
        updates=visible_updates,
        recent_posts=recent_posts,
        stats=stats,
    )


# ---------------------------------------------------------
# Profile
# ---------------------------------------------------------
@app.route("/profile")
@login_required
@account_active_required
def profile():
    return render_template("profile.html", user=current_user)


@app.route("/profile/<int:user_id>")
@login_required
@account_active_required
def view_profile(user_id):
    user = db.session.get(User, user_id) or abort(404)
    return render_template("profile.html", user=user)


@app.route("/edit_profile", methods=["GET", "POST"])
@login_required
@account_active_required
def edit_profile():
    if request.method == "POST":
        current_user.first_name = request.form.get("first_name", current_user.first_name).strip()
        current_user.surname = request.form.get("surname", current_user.surname).strip()
        current_user.phone_country_code = request.form.get("country_code", current_user.phone_country_code)
        current_user.phone_number = request.form.get("phone_number", current_user.phone_number).strip()
        current_user.bio = request.form.get("bio", "").strip()

        # Profile picture upload
        file = request.files.get("profile_picture")
        if file and file.filename:
            if allowed_file(file.filename):
                ext = file.filename.rsplit(".", 1)[1].lower()
                filename = secure_filename(f"user_{current_user.id}_{uuid.uuid4().hex[:8]}.{ext}")
                filepath = os.path.join(UPLOAD_FOLDER, filename)
                file.save(filepath)
                current_user.profile_picture = filename
            else:
                flash("Invalid file type. Only JPG, JPEG, PNG and WEBP are allowed.", "danger")

        db.session.commit()
        flash("Profile updated successfully.", "success")
        return redirect(url_for("profile"))

    return render_template("edit_profile.html", user=current_user, country_codes=COUNTRY_CODES)


@app.route("/remove_profile_picture", methods=["POST"])
@login_required
def remove_profile_picture():
    if current_user.profile_picture:
        old_path = os.path.join(UPLOAD_FOLDER, current_user.profile_picture)
        if os.path.exists(old_path):
            os.remove(old_path)
        current_user.profile_picture = ""
        db.session.commit()
    flash("Profile picture removed.", "success")
    return redirect(url_for("profile"))


@app.route("/change_password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not current_user.check_password(current_password):
            flash("Current password is incorrect.", "danger")
        elif new_password != confirm_password:
            flash("New passwords do not match.", "danger")
        elif len(new_password) < 6:
            flash("New password must be at least 6 characters.", "danger")
        else:
            current_user.set_password(new_password)
            current_user.force_password_change = False
            db.session.commit()
            flash("Password changed successfully.", "success")
            return redirect(url_for("profile"))

    return render_template("change_password.html")


# ---------------------------------------------------------
# Updates
# ---------------------------------------------------------
@app.route("/updates")
@login_required
@account_active_required
def updates():
    all_updates = Update.query.filter_by(published=True).order_by(Update.created_at.desc()).all()
    visible = [u for u in all_updates if u.visible_to(current_user.membership_plan)]
    return render_template("updates.html", updates=visible)


@app.route("/updates/create", methods=["POST"])
@login_required
@admin_required
def create_update():
    title = request.form.get("title", "").strip()
    content = request.form.get("content", "").strip()
    target_plan = request.form.get("target_plan", "BASIC").upper()
    if target_plan not in MEMBERSHIP_PLANS:
        target_plan = "BASIC"

    if not title or not content:
        flash("Title and content are required.", "danger")
        return redirect(url_for("updates"))

    update = Update(title=title, content=content, target_plan=target_plan,
                     author_id=current_user.id, published=True)
    db.session.add(update)
    db.session.commit()
    flash("Update published.", "success")
    return redirect(url_for("updates"))


@app.route("/updates/<int:update_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_update(update_id):
    update = db.session.get(Update, update_id) or abort(404)
    db.session.delete(update)
    db.session.commit()
    flash("Update deleted.", "success")
    return redirect(url_for("updates"))


@app.route("/updates/<int:update_id>/toggle", methods=["POST"])
@login_required
@admin_required
def toggle_update(update_id):
    update = db.session.get(Update, update_id) or abort(404)
    update.published = not update.published
    db.session.commit()
    return redirect(url_for("updates"))


# ---------------------------------------------------------
# Community
# ---------------------------------------------------------
@app.route("/community")
@login_required
@account_active_required
def community():
    posts = Post.query.order_by(Post.created_at.desc()).all()
    return render_template("community.html", posts=posts)


@app.route("/community/post", methods=["POST"])
@login_required
@account_active_required
def create_post():
    content = request.form.get("content", "").strip()
    if content:
        post = Post(content=content, author_id=current_user.id)
        db.session.add(post)
        db.session.commit()
        flash("Post shared.", "success")
    return redirect(url_for("community"))


@app.route("/community/post/<int:post_id>/delete", methods=["POST"])
@login_required
def delete_post(post_id):
    post = db.session.get(Post, post_id) or abort(404)
    if post.author_id != current_user.id and not current_user.is_admin():
        abort(403)
    db.session.delete(post)
    db.session.commit()
    flash("Post deleted.", "success")
    return redirect(url_for("community"))


@app.route("/community/post/<int:post_id>/edit", methods=["POST"])
@login_required
def edit_post(post_id):
    post = db.session.get(Post, post_id) or abort(404)
    if post.author_id != current_user.id:
        abort(403)
    new_content = request.form.get("content", "").strip()
    if new_content:
        post.content = new_content
        db.session.commit()
        flash("Post updated.", "success")
    return redirect(url_for("community"))


@app.route("/community/post/<int:post_id>/react", methods=["POST"])
@login_required
def react_post(post_id):
    post = db.session.get(Post, post_id) or abort(404)
    existing = Reaction.query.filter_by(user_id=current_user.id, post_id=post_id).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
    else:
        reaction = Reaction(user_id=current_user.id, post_id=post_id, type="like")
        db.session.add(reaction)
        db.session.commit()
    return redirect(url_for("community"))


@app.route("/community/post/<int:post_id>/comment", methods=["POST"])
@login_required
def add_comment(post_id):
    post = db.session.get(Post, post_id) or abort(404)
    content = request.form.get("content", "").strip()
    if content:
        comment = Comment(content=content, author_id=current_user.id, post_id=post.id)
        db.session.add(comment)
        db.session.commit()
    return redirect(url_for("community"))


@app.route("/community/comment/<int:comment_id>/delete", methods=["POST"])
@login_required
def delete_comment(comment_id):
    comment = db.session.get(Comment, comment_id) or abort(404)
    if comment.author_id != current_user.id and not current_user.is_admin():
        abort(403)
    db.session.delete(comment)
    db.session.commit()
    return redirect(url_for("community"))


# ---------------------------------------------------------
# Individual (direct) messages
# ---------------------------------------------------------
@app.route("/messages")
@login_required
@account_active_required
def messages_inbox():
    sent_to = db.session.query(Message.recipient_id).filter(Message.sender_id == current_user.id)
    recv_from = db.session.query(Message.sender_id).filter(Message.recipient_id == current_user.id)
    partner_ids = {row[0] for row in sent_to.union(recv_from).all()}

    conversations = []
    for pid in partner_ids:
        partner = db.session.get(User, pid)
        if not partner:
            continue
        last_message = Message.query.filter(
            db.or_(
                db.and_(Message.sender_id == current_user.id, Message.recipient_id == pid),
                db.and_(Message.sender_id == pid, Message.recipient_id == current_user.id),
            )
        ).order_by(Message.created_at.desc()).first()
        unread = Message.query.filter_by(sender_id=pid, recipient_id=current_user.id, read=False).count()
        conversations.append(dict(partner=partner, last_message=last_message, unread=unread))

    conversations.sort(
        key=lambda c: c["last_message"].created_at if c["last_message"] else datetime.min,
        reverse=True,
    )

    return render_template("messages_inbox.html", conversations=conversations)


@app.route("/messages/<int:user_id>")
@login_required
@account_active_required
def messages_chat(user_id):
    partner = db.session.get(User, user_id) or abort(404)
    if partner.id == current_user.id:
        abort(404)

    thread = Message.query.filter(
        db.or_(
            db.and_(Message.sender_id == current_user.id, Message.recipient_id == user_id),
            db.and_(Message.sender_id == user_id, Message.recipient_id == current_user.id),
        )
    ).order_by(Message.created_at.asc()).all()

    unread = Message.query.filter_by(sender_id=user_id, recipient_id=current_user.id, read=False).all()
    for m in unread:
        m.read = True
    if unread:
        db.session.commit()

    return render_template("messages_chat.html", partner=partner, thread=thread)


@app.route("/messages/<int:user_id>/send", methods=["POST"])
@login_required
@account_active_required
def messages_send(user_id):
    partner = db.session.get(User, user_id) or abort(404)
    if partner.id == current_user.id:
        abort(404)

    content = (request.json.get("content", "").strip()
               if request.is_json else request.form.get("content", "").strip())
    if not content:
        return jsonify({"error": "Message cannot be empty."}), 400

    msg = Message(sender_id=current_user.id, recipient_id=user_id, content=content)
    db.session.add(msg)
    db.session.commit()

    return jsonify({
        "id": msg.id,
        "content": msg.content,
        "sender_id": msg.sender_id,
        "created_at": msg.created_at.strftime("%H:%M"),
    })


@app.route("/messages/<int:user_id>/poll")
@login_required
@account_active_required
def messages_poll(user_id):
    db.session.get(User, user_id) or abort(404)
    after_id = request.args.get("after", 0, type=int)

    new_messages = Message.query.filter(
        Message.id > after_id,
        db.or_(
            db.and_(Message.sender_id == current_user.id, Message.recipient_id == user_id),
            db.and_(Message.sender_id == user_id, Message.recipient_id == current_user.id),
        )
    ).order_by(Message.created_at.asc()).all()

    unread_incoming = [m for m in new_messages if m.recipient_id == current_user.id and not m.read]
    for m in unread_incoming:
        m.read = True
    if unread_incoming:
        db.session.commit()

    return jsonify({
        "messages": [
            dict(id=m.id, content=m.content, sender_id=m.sender_id,
                 created_at=m.created_at.strftime("%H:%M"))
            for m in new_messages
        ]
    })


# ---------------------------------------------------------
# Search
# ---------------------------------------------------------
@app.route("/search")
@login_required
@account_active_required
def search():
    query = request.args.get("q", "").strip()
    members, posts, updates_found = [], [], []

    if query:
        like = f"%{query}%"
        members = User.query.filter(
            db.or_(User.first_name.ilike(like), User.surname.ilike(like))
        ).limit(20).all()

        posts = Post.query.filter(Post.content.ilike(like)).limit(20).all()

        all_updates = Update.query.filter(
            db.or_(Update.title.ilike(like), Update.content.ilike(like))
        ).filter_by(published=True).limit(20).all()
        updates_found = [u for u in all_updates if u.visible_to(current_user.membership_plan)]

    return render_template("search.html", query=query, members=members,
                            posts=posts, updates=updates_found)


# ---------------------------------------------------------
# BigThinkers AI
# ---------------------------------------------------------
@app.route("/ai")
@login_required
@account_active_required
def ai():
    ai_configured = bool(os.environ.get("OPENAI_API_KEY"))
    return render_template("ai.html", ai_configured=ai_configured)


@app.route("/ai/chat", methods=["POST"])
@login_required
@account_active_required
def ai_chat():
    api_key = os.environ.get("OPENAI_API_KEY")
    user_message = request.json.get("message", "").strip() if request.is_json else ""

    if not user_message:
        return jsonify({"error": "Please enter a message."}), 400

    if not api_key:
        return jsonify({
            "reply": "BigThinkers AI is not fully configured yet. An administrator needs to "
                      "add an OPENAI_API_KEY to the server's environment variables. In the "
                      "meantime, feel free to reach out to a BigThinkers co-founder on WhatsApp "
                      "using the buttons below."
        })

    try:
        import requests
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": (
                        "You are BigThinkers AI, a helpful assistant for the BigThinkers "
                        "community. Help members with education, business, entrepreneurship, "
                        "jobs, CV writing, interview preparation, career guidance, personal "
                        "development, skills, business ideas, and leadership. Be encouraging, "
                        "practical, and concise."
                    )},
                    {"role": "user", "content": user_message},
                ],
                "max_tokens": 600,
            },
            timeout=30,
        )
        data = response.json()

        if "error" in data:
            # OpenAI rejected the request (bad key, no billing, rate limit, etc.)
            app.logger.error("OpenAI API error: %s", data["error"])
            return jsonify({
                "reply": "BigThinkers AI hit an error talking to OpenAI: "
                         + str(data["error"].get("message", "unknown error"))
            })

        reply = data["choices"][0]["message"]["content"]
        return jsonify({"reply": reply})
    except Exception as e:
        app.logger.exception("BigThinkers AI request failed")
        return jsonify({
            "reply": "Sorry, BigThinkers AI couldn't process that right now. "
                      "Please try again shortly, or contact a co-founder on WhatsApp. "
                      f"(debug: {e})"
        })


# ---------------------------------------------------------
# Admin
# ---------------------------------------------------------
@app.route("/admin")
@login_required
@admin_required
def admin():
    users = User.query.order_by(User.created_at.desc()).all()

    stats = dict(
        total_members=User.query.count(),
        basic=User.query.filter_by(membership_plan="BASIC").count(),
        premium=User.query.filter_by(membership_plan="PREMIUM").count(),
        vip=User.query.filter_by(membership_plan="VIP").count(),
        pending=User.query.filter_by(subscription_status="pending").count(),
        active=User.query.filter_by(subscription_status="active").count(),
        frozen=User.query.filter_by(account_status="frozen").count(),
        blocked=User.query.filter_by(account_status="blocked").count(),
        total_posts=Post.query.count(),
        total_updates=Update.query.count(),
    )

    return render_template("admin.html", users=users, stats=stats,
                            positions=ADMIN_POSITIONS, plans=MEMBERSHIP_PLANS)


def _protect_main_admin(user):
    if user.is_main_admin():
        flash("The main administrator account is protected and cannot be modified this way.", "danger")
        return True
    return False


@app.route("/admin/user/<int:user_id>/approve", methods=["POST"])
@login_required
@admin_required
def approve_user(user_id):
    user = db.session.get(User, user_id) or abort(404)
    user.subscription_status = "active"
    user.approved_at = datetime.utcnow()
    db.session.commit()
    flash(f"{user.full_name()}'s subscription has been approved.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/user/<int:user_id>/freeze", methods=["POST"])
@login_required
@admin_required
def freeze_user(user_id):
    user = db.session.get(User, user_id) or abort(404)
    if _protect_main_admin(user):
        return redirect(url_for("admin"))
    user.account_status = "frozen" if user.account_status != "frozen" else "active"
    db.session.commit()
    flash(f"{user.full_name()}'s account status updated.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/user/<int:user_id>/block", methods=["POST"])
@login_required
@admin_required
def block_user(user_id):
    user = db.session.get(User, user_id) or abort(404)
    if _protect_main_admin(user):
        return redirect(url_for("admin"))
    user.account_status = "blocked" if user.account_status != "blocked" else "active"
    db.session.commit()
    flash(f"{user.full_name()}'s account status updated.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/user/<int:user_id>/promote", methods=["POST"])
@login_required
@admin_required
def promote_user(user_id):
    user = db.session.get(User, user_id) or abort(404)
    position = request.form.get("position", "Administrator")
    if position not in ADMIN_POSITIONS:
        position = "Other"
    user.role = "admin"
    user.position = position
    db.session.commit()
    flash(f"{user.full_name()} promoted to {position}.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/user/<int:user_id>/demote", methods=["POST"])
@login_required
@admin_required
def demote_user(user_id):
    user = db.session.get(User, user_id) or abort(404)
    if _protect_main_admin(user):
        return redirect(url_for("admin"))
    user.role = "member"
    user.position = None
    db.session.commit()
    flash(f"{user.full_name()} demoted to member.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/user/<int:user_id>/edit", methods=["POST"])
@login_required
@admin_required
def admin_edit_user(user_id):
    user = db.session.get(User, user_id) or abort(404)

    user.first_name = request.form.get("first_name", user.first_name).strip()
    user.surname = request.form.get("surname", user.surname).strip()
    user.phone_number = request.form.get("phone_number", user.phone_number)
    user.bio = request.form.get("bio", user.bio)

    plan = request.form.get("membership_plan", user.membership_plan).upper()
    if plan in MEMBERSHIP_PLANS:
        user.membership_plan = plan

    status = request.form.get("account_status", user.account_status)
    if status in ("active", "frozen", "blocked") and not (user.is_main_admin() and status != "active"):
        user.account_status = status

    db.session.commit()
    flash(f"{user.full_name()}'s details updated.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/user/<int:user_id>/reset_password", methods=["POST"])
@login_required
@admin_required
def admin_reset_password(user_id):
    user = db.session.get(User, user_id) or abort(404)
    temp_password = uuid.uuid4().hex[:10]
    user.set_password(temp_password)
    user.force_password_change = True
    db.session.commit()
    flash(f"Temporary password for {user.full_name()}: {temp_password} "
          f"(share this securely — it will not be shown again).", "success")
    return redirect(url_for("admin"))


# ---------------------------------------------------------
# Error handlers
# ---------------------------------------------------------
@app.errorhandler(403)
def forbidden(e):
    return render_template("error.html", code=403,
                            message="You do not have permission to access this page."), 403


@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", code=404,
                            message="The page you're looking for doesn't exist."), 404


@app.errorhandler(500)
def server_error(e):
    return render_template("error.html", code=500,
                            message="Something went wrong on our end. Please try again."), 500


# ---------------------------------------------------------
# Database initialization
# ---------------------------------------------------------
def _ensure_schema():
    """Create any new tables, and lightly auto-migrate the `users` table
    so an existing database (from before this update) gets the new
    reset-code columns without losing any existing member data."""
    db.create_all()
    with db.engine.connect() as conn:
        existing_cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(users)")}
        if "reset_code" not in existing_cols:
            conn.exec_driver_sql("ALTER TABLE users ADD COLUMN reset_code VARCHAR(10)")
        if "reset_code_expires" not in existing_cols:
            conn.exec_driver_sql("ALTER TABLE users ADD COLUMN reset_code_expires DATETIME")
        conn.commit()


with app.app_context():
    _ensure_schema()


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
