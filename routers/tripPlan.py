from fastapi import FastAPI, File, UploadFile, Form, Depends, HTTPException, Request, APIRouter
from sqlalchemy.orm import Session
from models.models import tripPlans
from database import sqldb
import base64
import uuid


router = APIRouter()

@router.get('/getTripPlans', description = "mySQL tripPlans Table 접근해서 정보 가져오기, tripId는 선택사항")
async def getTripPlansTable(
    tripId: str = None,
    session: Session = Depends(sqldb.sessionmaker)):
    try:
        query = session.query(tripPlans)
        if tripId is not None:
            query = query.filter(tripPlans.tripId == tripId)
        tripplans_data = query.all()
        return {"result code": 200, "response": tripplans_data}
    finally:
        session.close()

@router.get('/getTripPlansDate', description = "mySQL tripPlans Table 접근해서 정보 가져오기, date, tripId 필수사항")
async def getTripPlansDateTable(
    date: str ,
    tripId : str,
    session: Session = Depends(sqldb.sessionmaker)):
    try:
        query = session.query(tripPlans)
        if date is not None and tripId is not None:
            query = query.filter(tripPlans.tripId == tripId, tripPlans.date == date)
        tripplans_data = query.all()
        return {"result code": 200, "response": tripplans_data}
    finally:
        session.close()


@router.post('/insertTripPlans', description="mySQL tripPlans Table에 추가, planId는 uuid로 생성")
async def insertTripPlansTable(
    userId :  str = Form(...),
    tripId :  str = Form(...),
    title :  str = Form(...),
    date : str = Form(...),
    time : str = Form(...),
    place :  str = Form(...),
    address : str = Form(...),
    latitude : str = Form(...),
    longitude : str = Form(...),
    description : str = Form(...),
    crewId : str = Form(None),
    session: Session = Depends(sqldb.sessionmaker)
):
    try:
        planId = str(uuid.uuid4())
        new_tripPlan = tripPlans(planId=planId, userId=userId, tripId=tripId, title=title, date=date, time=time, place=place, address=address, latitude=latitude, longitude=longitude, description=description, crewId=crewId)
        session.add(new_tripPlan)
        session.commit()
        session.refresh(new_tripPlan)
        return {"result code": 200, "response": planId}
    finally:
        session.close()