"""Data access for revoked JWT identifiers."""

from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.revoked_token import RevokedToken
from app.utils.datetime import ensure_utc, utc_now


class RevokedTokenRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(
        self,
        jti: str,
        expires_at: datetime,
        user_id: int | None = None,
        commit: bool = True,
    ) -> RevokedToken:
        entry = RevokedToken(jti=jti, user_id=user_id, expires_at=ensure_utc(expires_at))
        self.session.add(entry)
        if commit:
            self.session.commit()
        else:
            self.session.flush()
        return entry

    def is_revoked(self, jti: str) -> bool:
        statement = select(RevokedToken.id).where(RevokedToken.jti == jti)
        return self.session.execute(statement).scalar_one_or_none() is not None

    def purge_expired(self, now: datetime | None = None) -> int:
        """Delete entries for tokens that already expired on their own."""
        reference = ensure_utc(now) or utc_now()
        result = self.session.execute(
            delete(RevokedToken).where(RevokedToken.expires_at < reference)
        )
        self.session.commit()
        return result.rowcount or 0
