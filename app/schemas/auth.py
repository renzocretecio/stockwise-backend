from pydantic import BaseModel, EmailStr

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class UserResponse(BaseModel):
    id: str
    email: str
    first_name: str
    
    class Config:
        from_attributes = True

class BusinessResponse(BaseModel):
    id: str
    name: str
    slug: str
    
    class Config:
        from_attributes = True