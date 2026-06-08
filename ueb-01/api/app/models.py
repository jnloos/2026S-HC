"""SQLModel tables.

The Digital Signage prototype has two domain entities:

- ``Pool`` — a named bucket of HTML snippets.
- ``Content`` — a single HTML snippet belonging to one pool (1:n).

The HTML itself lives on disk under ``storage/pools/<pool_id>/<content_id>.html``;
only metadata is stored in the database.
"""
from sqlmodel import Field, Relationship, SQLModel


class Pool(SQLModel, table=True):
    __tablename__ = "pools"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True)
    description: str = ""

    contents: list["Content"] = Relationship(
        back_populates="pool",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class Content(SQLModel, table=True):
    __tablename__ = "contents"

    id: int | None = Field(default=None, primary_key=True)
    pool_id: int = Field(foreign_key="pools.id", index=True, ondelete="CASCADE")
    name: str
    # Short "what is this content for?" hint — used by the selection LLM and
    # by the edge variant. Especially important when the HTML is image-heavy
    # and the snippet alone doesn't convey the audience/context.
    description: str = ""

    pool: Pool | None = Relationship(back_populates="contents")
