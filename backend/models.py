from sqlalchemy import Column, Any, ForeignKey, Integer, String, Boolean, Text, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from database_handling import Base


class Doc(Base):
    __tablename__ = "doc"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False, index=True)
    content = Column(Text, nullable=False)
    chunked = Column(Boolean, default=False, nullable=False, index=True)
    repo_id = Column(Integer, ForeignKey("repo.id"))
    repo = relationship("Repo", back_populates="docs")


class Repo(Base):
    __tablename__ = "repo"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    url = Column(String, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    description = Column(Text, nullable=True)
    docs = relationship("Doc", back_populates="repo")
    error = Column(String, nullable=True)
