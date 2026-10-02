from pydantic import BaseModel


class User(BaseModel):
    user_id: str
    is_admin: bool = False
