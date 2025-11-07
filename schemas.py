from pydantic import BaseModel, Field, EmailStr
from typing import Optional, Literal
from datetime import datetime

# Each model name defines a collection name in lowercase
# student, payment, test, certificate

class Student(BaseModel):
    npm: str = Field(..., description="Nomor Pokok Mahasiswa")
    name: str
    email: EmailStr

class Payment(BaseModel):
    npm: str
    name: str
    email: EmailStr
    file_name: Optional[str] = None
    file_mime: Optional[str] = None
    file_data_b64: Optional[str] = None
    status: Literal['pending','approved','rejected'] = 'pending'
    verified_by: Optional[str] = None
    verified_at: Optional[datetime] = None

class Test(BaseModel):
    npm: str
    attempt: int = Field(..., ge=1)
    score: Optional[float] = None
    status: Literal['pass','fail']
    taken_at: Optional[datetime] = None

class Certificate(BaseModel):
    npm: str
    attempt: int
    issued_at: Optional[datetime] = None
