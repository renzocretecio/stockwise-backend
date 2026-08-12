from sqlalchemy.ext.declarative import declarative_base
import uuid
from sqlalchemy import Column, UUID as UUID_Type

Base = declarative_base()

# Helper for UUID columns
def uuid_column(primary_key=False):
    return Column(UUID_Type(as_uuid=True), primary_key=primary_key, default=uuid.uuid4)