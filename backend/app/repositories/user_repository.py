"""Data access for users. Keeps SQL out of services and routes."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User


class UserRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, user_id: int) -> User | None:
        return self.session.get(User, user_id)

    def get_by_username(self, username: str) -> User | None:
        statement = select(User).where(User.username == username)
        return self.session.execute(statement).scalar_one_or_none()

    def get_by_email(self, email: str) -> User | None:
        statement = select(User).where(User.email == email)
        return self.session.execute(statement).scalar_one_or_none()

    def list_users(self) -> list[User]:
        statement = select(User).order_by(User.id)
        return list(self.session.execute(statement).scalars())

    def count_active_admins(self) -> int:
        statement = (
            select(User.id)
            .join(User.role)
            .where(User.is_active.is_(True), User.role.has(name="admin"))
        )
        return len(list(self.session.execute(statement).scalars()))

    def update_last_login(self, user: User) -> None:
        user.last_login_at = datetime.now(timezone.utc)
        self.session.commit()
