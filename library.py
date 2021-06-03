from flask import Flask, render_template, flash, redirect, request, url_for
from flask_sqlalchemy import SQLAlchemy

from datetime import datetime, timedelta
from functools import wraps

from flask.blueprints import Blueprint
from flask.views import MethodView
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash


app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///market.db'
db = SQLAlchemy(app)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255))
    email = db.Column(db.String(255), unique=True)
    password = db.Column(db.String(255))
    book = db.relationship("Copy", backref="issue", lazy=True)
    admin = db.Column(db.Boolean, default=False)


class Book(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), unique=True)
    author = db.Column(db.String(255))
    description = db.Column(db.Text)
    copy = db.relationship(
        "Copy", backref=db.backref("posts", lazy=True), cascade="all,delete"
    )
    total_copy = db.Column(db.Integer)
    issued_copy = db.Column(db.Integer)
    present_copy = db.Column(db.Integer)


class Copy(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date_added = db.Column(db.DateTime())
    issued_by = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=True, default=None
    )
    date_issued = db.Column(db.DateTime(), default=None)
    date_return = db.Column(db.DateTime(), default=None)
    book = db.Column(db.Integer, db.ForeignKey("book.id"))

main = Blueprint("main", __name__)


def requires_admin(f):
    """Checks if user has admin access"""

    @wraps(f)
    def wrapped(*args, **kwargs):
        if current_user.admin:
            return f(*args, **kwargs)
        return unauthorized()

    return wrapped


@login_manager.user_loader
def load_user(user_id: int):
    return User.query.get(user_id)


@main.route("/", methods=["GET"])
def index():
    """Home Page"""
    books = Book.query.all()
    if books:
        return render_template("index.html", year=datetime.now().year, books=books)
    flash("No books are in library!")
    return render_template("index.html", year=datetime.now().year)


class LoginView(MethodView):
    def get(self):
        return render_template("login.html", year=datetime.now().year)

    def post(self):
        email = request.form.get("email")
        password = request.form.get("password")
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            if request.args.get("next"):
                return redirect(request.args.get("next"))
            return redirect(url_for("main.dashboard"))
        flash("Invalid Credentials!")
        return redirect(url_for("main.login"))


class RegisterView(MethodView):
    def get(self):
        return render_template("register.html", year=datetime.now().year)

    def post(self):
        name = request.form.get("name")
        email = request.form.get("email")
        password = generate_password_hash(request.form.get("password"), method="sha256")
        if User.query.filter_by(email=email).first():
            flash("User already exists!")
            return redirect(url_for("main.register"))
        user = User(name=name, email=email, password=password)
        db.session.add(user)
        db.session.commit()
        login_user(user)
        if request.args.get("next"):
            return redirect(request.args.get("next"))
        return redirect(url_for("main.dashboard"))


class AdminView(MethodView):
    def get(self):
        return render_template("admin.html", year=datetime.now().year)

    def post(self):
        email = request.form.get("email")
        password = request.form.get("password")
        user = User.query.filter_by(email=email, admin=True).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            if request.args.get("next"):
                return redirect(request.args.get("next"))
            return redirect(url_for("main.dashboard"))
        flash("Invalid Credentials!")
        return redirect(url_for("main.admin"))


@main.route("/dashboard", methods=["GET"])
@login_required
def dashboard():
    copies = Copy.query.filter_by(issued_by=current_user.id).all()
    if copies:
        return render_template("dashboard.html", year=datetime.now().year, books=copies)

    flash("You don't have books issued!")
    return render_template("dashboard.html", year=datetime.now().year)


@main.route("/admin/dashboard", methods=["GET"])
@login_required
@requires_admin
def admin_dashboard():
    books = Book.query.all()
    if books:
        return render_template(
            "admin_dashboard.html", books=books, year=datetime.now().year
        )
    flash("No books are there in library!")
    return render_template("admin_dashboard.html", year=datetime.now().year)


class AddBookView(MethodView):
    def get(self):
        return render_template("add_book.html", year=datetime.now().year)

    def post(self):
        name = request.form.get("name")
        author = request.form.get("author")
        description = request.form.get("description")
        number = int(request.form.get("number"))
        book = Book.query.filter_by(name=name).first()
        if book:
            flash("Book already exists!")
            return redirect(url_for("main.add_book"))
        book = Book(
            name=name,
            author=author,
            description=description,
            total_copy=number,
            present_copy=number,
            issued_copy=0,
        )

        for _ in range(number):
            copy = Copy(date_added=datetime.now())
            book.copy.append(copy)
            db.session.add(book)
        db.session.commit()
        flash("Book added successfully!")
        return redirect(url_for("main.admin_dashboard"))


@main.route("/admin/logout")
@login_required
@requires_admin
def admin_logout():
    return redirect(url_for("main.index"))


class IssueBookView(MethodView):
    def get(self):
        books = Book.query.filter(Book.present_copy > 0).all()
        if books:
            return render_template(
                "issue.html", books=Book.query.all(), year=datetime.now().year
            )
        flash("No books are currently available!")
        return render_template(
            "issue.html", year=datetime.now().year, books=Book.query.all()
        )

    def post(self):
        book_id = int(request.form.get("book"))
        book = Copy.query.filter_by(book=book_id, issued_by=None).first()
        book.issued_by = current_user.id
        book.copies.issued_copy += 1
        book.copies.present_copy -= 1
        book.date_issued = datetime.now()
        book.date_return = datetime.now() + timedelta(days=1)
        db.session.commit()
        flash("Book issued successfully!")
        return redirect(url_for("main.dashboard"))


class ReturnBookView(MethodView):
    def get(self):
        copies = Copy.query.filter_by(issued_by=current_user.id).all()
        if copies:
            return render_template(
                "return.html", books=copies, year=datetime.now().year
            )

        flash("You don't have any books issued!")
        return render_template(
            "return.html", year=datetime.now().year, books=Book.query.all()
        )

    def post(self):
        book_id = request.form.get("book")
        book = Copy.query.filter_by(
            book=int(book_id), issued_by=current_user.id
        ).first()
        book.issued_by = None
        book.date_issued = None
        book.date_return = None
        book.copies.issued_copy -= 1
        book.copies.present_copy += 1
        db.session.commit()
        flash("Book returned successfully!")
        return redirect(url_for("main.dashboard"))


class RemoveBookView(MethodView):
    def get(self):
        books = Book.query.filter_by(issued_copy=0).all()
        if books:
            return render_template(
                "remove_book.html", year=datetime.now().year, books=Book.query.all()
            )

        flash("No books are available to be removed!")
        return render_template(
            "remove_book.html", year=datetime.now().year, books=Book.query.all()
        )

    def post(self):
        book_id = int(request.form.get("book"))
        book = Book.query.filter_by(id=book_id).first()
        db.session.delete(book)
        db.session.commit()
        flash("Book removed successfully!")
        return redirect(url_for("main.admin_dashboard"))


main.add_url_rule("/register", view_func=RegisterView.as_view("register"))
main.add_url_rule("/login", view_func=LoginView.as_view("login"))
main.add_url_rule("/admin", view_func=AdminView.as_view("admin"))
main.add_url_rule(
    "/add/book",
    view_func=login_required(requires_admin(AddBookView.as_view("add_book"))),
)
main.add_url_rule(
    "/return/book", view_func=login_required(ReturnBookView.as_view("return_book"))
)
main.add_url_rule(
    "/remove/book", view_func=login_required(RemoveBookView.as_view("remove_book"))
)
main.add_url_rule(
    "/issue/book", view_func=login_required(IssueBookView.as_view("issue_book"))
)


@main.route("/logout", methods=["GET"])
@login_required
def logout():
    logout_user()
    return redirect(url_for("main.index"))


@login_manager.unauthorized_handler
def unauthorized():
    flash("You are not authorized to access the content!")
    return redirect(url_for("main.login"))
