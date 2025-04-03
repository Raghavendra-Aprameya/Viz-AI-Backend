from app.models.schema_models import UserModel
from sqlalchemy.orm import Session
from app.core.db import get_db
from fastapi import APIRouter, status, Depends, Response, Request, HTTPException
from sqlalchemy.exc import IntegrityError
from pydantic import ValidationError
# from fastapi.responses import JSONResponse
import bcrypt


async def register_user(user: UserModel, response: Response, db: Session = Depends(get_db)):
    try:
      res = await db.query(UserModel).filter(UserModel.username==user.username).first()
      if res:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail="User already exists")
      else: 
        # Hash password with bcrypt
        salt = bcrypt.gensalt()
        user.password = bcrypt.hashpw(user.password.encode(), salt).decode()
        new_user = UserModel(**user.model_dump())
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        response.status_code = status.HTTP_201_CREATED
        return new_user

    except Exception as e:
      raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail=e)
    

  
    
    


