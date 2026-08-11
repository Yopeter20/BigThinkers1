from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

# ---------------------------------------------------------
# Positions available for admins (Section 38-40)
# ---------------------------------------------------------
ADMIN_POSITIONS = [
    "Super Administrator",
    "Administrator",
    "Secretary",
    "Treasurer",
    "Moderator",
    "Community Manager",
    "Content Manager",
    "Editor",
    "Support",
    "Other",
]

BADGE_ICONS = {
    "Super Administrator": "👑",
    "Administrator": "🏅",
    "Secretary": "📋",
    "Treasurer": "💰",
    "Moderator": "🛡",
    "Community Manager": "🌐",
    "Content Manager": "✍",
    "Editor": "📝",
    "Support": "🎧",
    "Other": "⭐",
}

MEMBERSHIP_PLANS = ["BASIC", "PREMIUM", "VIP"]
PLAN_RANK = {"BASIC": 1, "PREMIUM": 2, "VIP": 3}


class User(db.Model, UserMixin):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)

    first_name = db.Column(db.String(80), nullable=False)
    surname = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False, index=True)
    phone_country_code = db.Column(db.String(10), default="+260")
    phone_number = db.Column(db.String(30))

    password_hash = db.Column(db.String(255), nullable=False)

    membership_plan = db.Column(db.String(20), default="BASIC")  # BASIC / PREMIUM / VIP
    subscription_status = db.Column(db.String(20), default="pending")  # pending / active
    approved_at = db.Column(db.DateTime)

    role = db.Column(db.String(20), default="member")  # member / admin
    position = db.Column(db.String(50))  # Secretary, Treasurer, etc.

    account_status = db.Column(db.String(20), default="active")  # active / frozen / blocked

    bio = db.Column(db.Text, default="")
    profile_picture = db.Column(db.String(255), default="")

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    force_password_change = db.Column(db.Boolean, default=False)

    # Password reset via emailed code
    reset_code = db.Column(db.String(10))
    reset_code_expires = db.Column(db.DateTime)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def full_name(self):
        return f"{self.first_name} {self.surname}"

    def is_admin(self):
        return self.role == "admin"

    def is_main_admin(self):
        from flask import current_app
        return self.email.lower() == current_app.config["MAIN_ADMIN_EMAIL"].lower()

    def badge_icon(self):
        return BADGE_ICONS.get(self.position, "🏅") if self.is_admin() else ""

    def profile_completion(self):
        fields = [self.first_name, self.surname, self.email, self.phone_number,
                  self.bio, self.profile_picture]
        filled = sum(1 for f in fields if f)
        return int((filled / len(fields)) * 100)


class Update(db.Model):
    __tablename__ = "updates"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    image = db.Column(db.String(255))
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    author = db.relationship("User")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    target_plan = db.Column(db.String(20), default="BASIC")  # BASIC / PREMIUM / VIP
    published = db.Column(db.Boolean, default=True)

    def visible_to(self, plan):
        """Higher plans can see lower-tier-targeted updates too."""
        return PLAN_RANK.get(plan, 0) >= PLAN_RANK.get(self.target_plan, 1)


class Post(db.Model):
    __tablename__ = "posts"

    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    author = db.relationship("User")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    comments = db.relationship("Comment", backref="post", cascade="all, delete-orphan")
    reactions = db.relationship("Reaction", backref="post", cascade="all, delete-orphan")

    def reaction_count(self):
        return len(self.reactions)

    def user_has_reacted(self, user_id):
        return any(r.user_id == user_id for r in self.reactions)


class Comment(db.Model):
    __tablename__ = "comments"

    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    author = db.relationship("User")
    post_id = db.Column(db.Integer, db.ForeignKey("posts.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Reaction(db.Model):
    __tablename__ = "reactions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    post_id = db.Column(db.Integer, db.ForeignKey("posts.id"))
    type = db.Column(db.String(20), default="like")

    __table_args__ = (db.UniqueConstraint("user_id", "post_id", name="unique_user_post_reaction"),)


class Message(db.Model):
    """A single direct message between two members (individual chat)."""
    __tablename__ = "messages"

    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    recipient_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    read = db.Column(db.Boolean, default=False)

    sender = db.relationship("User", foreign_keys=[sender_id])
    recipient = db.relationship("User", foreign_keys=[recipient_id])
