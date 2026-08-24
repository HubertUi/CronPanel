"""Data access for roles."""

from sqlalchemy.orm import Session

from app.models.role import Role


class RoleRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_name(self, name: str) -> Role | None:
        return self.session.query(Role).filter(Role.name == name).one_or_none()
