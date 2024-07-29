import os
import json
import openai
from serpapi import GoogleSearch
from deep_translator import GoogleTranslator
from sqlalchemy.ext.declarative import declarative_base
from pymongo import MongoClient
import re
import uuid
from sqlalchemy import *
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine,Column, String, INT,  FLOAT, LargeBinary, JSON
import google.generativeai as genai
from database import sqldb, OPENAI_API_KEY, DB_URL, mongodb_url, GEMINI_API_KEY, SERP_API_KEY,db
from models.models import myTrips, tripPlans
from langchain.memory import ConversationBufferMemory
from langchain.schema import BaseMessage, AIMessage, HumanMessage, SystemMessage

# ConversationBufferMemory 초기화
if 'memory' not in globals():
    memory = ConversationBufferMemory()

def message_to_dict(msg: BaseMessage):
    if isinstance(msg, HumanMessage):
        return {"role": "user", "content": msg.content}
    elif isinstance(msg, AIMessage):
        return {"role": "assistant", "content": msg.content}
    elif isinstance(msg, SystemMessage):
        return {"role": "system", "content": msg.content}
    else:
        raise ValueError(f"Unknown message type: {type(msg)}")

def call_openai_function(query: str, userId: str, tripId: str):
    
    memory.save_context({"input": query}, {"output": ""})
    print(memory)
    
    # 메시지를 적절한 형식으로 변환
    messages = [
        {"role": "system", "content": "You are a helpful assistant that helps users plan their travel plans."},
    ] + [message_to_dict(msg) for msg in memory.chat_memory.messages] + [
        {"role": "user", "content": query}
    ]
    
    response = openai.ChatCompletion.create(
        model="gpt-4-0613",
        messages=messages,
        functions=[
            {
                "name": "search_places",
                "description": "Search for various types of places based on user query",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query for finding places"
                        },
                        "userId": {
                            "type": "string",
                            "description": "The user ID for the search context"
                        },
                        "tripId": {
                            "type": "string",
                            "description": "The trip ID for the search context"
                        }
                    },
                    "required": ["query", "userId", "tripId"]
                }
            },
            {
                "name": "just_chat",
                "description": "Respond to general questions and provide information",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The user's general query"
                        }
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "save_place",
                "description": "query에서 숫자만 추출해 SerpData의 mongoDB데이터를 가져와 SavePlace mongoDB에 저장",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "사용자가 숫자와 함께 저장,추가해줘 혹은 갈래 라는 쿼리를 입력했을 시에 실행"
                        }
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "save_plan",
                "description": "SavePlace의 placeData를 mysql tripPlans Table에 저장",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "사용자가 여행 일정을 만들어줘 혹은 이정도면 충분해 이제 저장할래 이런 말을 했을 때에 실행"
                        }
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "check_trip_plan",
                "description": "Get the trip plan details and confirm with the user",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "user_id": {
                            "type": "string",
                            "description": "User ID"
                        },
                        "trip_title": {
                            "type": "string",
                            "description": "Title of the trip"
                        },
                        "date": {
                            "type": "string",
                            "description": "Date of the trip"
                        },
                        "plan_title": {
                            "type": "string",
                            "description": "Title of the trip plan"
                        }
                    },
                    "required": ["user_id", "trip_title", "date", "plan_title"]
                }
            },
            {
                "name": "update_trip_plan",
                "description": "Update a trip plan with the given details",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "user_id": {
                            "type": "string",
                            "description": "User ID"
                        },
                        "trip_title": {
                            "type": "string",
                            "description": "Title of the trip"
                        },
                        "date": {
                            "type": "string",
                            "description": "Date of the trip"
                        },
                        "plan_title": {
                            "type": "string",
                            "description": "Title of the trip plan"
                        },
                        "new_time": {
                            "type": "string",
                            "description": "New time for the trip plan"
                        }
                    },
                    "required": ["user_id", "trip_title", "date", "plan_title", "new_time"]
                }
            }
        ],
        function_call="auto"
    )

    try:
        function_call = response.choices[0].message["function_call"]
        function_name = function_call["name"]
        
        # 호출된 함수 이름을 출력
        print(f"Calling function: {function_name}")

        if function_name == "search_places":
            args = json.loads(function_call["arguments"])
            search_query = args["query"]
            result = search_places(search_query, userId, tripId)
        elif function_name == "just_chat":
            args = json.loads(function_call["arguments"])
            result = just_chat(args["query"])
        elif function_name == "save_place":
            args = json.loads(function_call["arguments"])
            result = extractNumbers(args["query"], userId, tripId)
        elif function_name == "save_plan":
            args = json.loads(function_call["arguments"])
            result = savePlans(userId, tripId)
        elif function_name == "update_trip_plan":
            args = json.loads(function_call["arguments"])
            result = update_trip_plan(args["user_id"], args["trip_title"], args["date"], args["plan_title"], args["new_time"])
        elif function_name == "check_trip_plan":
            args = json.loads(function_call["arguments"])
            result = check_trip_plan(args["user_id"], args["trip_title"], args["plan_title"], args["date"])
        else:
            result = response.choices[0].message["content"]
    except KeyError:
        result = response.choices[0].message["content"]

    # 대화 메모리에 응답 추가
    memory.save_context({"input": query}, {"output": result})

    return result


def search_places(query: str, userId, tripId):
    params = {
        "engine": "google_maps",
        "q": query,
        "hl": "en",
        "api_key": SERP_API_KEY
    }
    search = GoogleSearch(params)
    results_data = search.get_dict()

    return parseSerpData(results_data, userId, tripId)

def parseSerpData(data, userId, tripId):
    if 'local_results' not in data:
        return ""
    
    translator = GoogleTranslator(source='en', target='ko')
    parsed_results = []
    formatted_results = []
    serp_collection = db['SerpData']
    
    for idx, result in enumerate(data['local_results'], 1):
        title = result.get('title')
        rating = result.get('rating')
        address = result.get('address')
        gps_coordinates = result.get('gps_coordinates', {})
        latitude = gps_coordinates.get('latitude')
        longitude = gps_coordinates.get('longitude')
        description = result.get('description', 'No description available.')
        translated_description = translator.translate(description)
        price = result.get('price', None)

        if not address or not latitude or not longitude:
            continue

        place_data = {
            "title": title,
            "rating": rating,
            "address": address,
            "latitude": latitude,
            "longitude": longitude,
            "description": translated_description,
            "price": price,
            "date": None,
            "time": None
        }
        
        parsed_results.append(place_data)
        
        formatted_place = f"{idx}. 장소 이름: {title}\n    별점: {rating}\n    주소: {address}\n    설명: {translated_description}\n"
        if price:
            formatted_place += f"    가격: {price}\n"
        
        formatted_results.append(formatted_place)
    
    document = {
        "userId": userId,
        "tripId": tripId,
        "data": parsed_results
    }

    serp_collection.update_one(
        {"userId": userId, "tripId": tripId},
        {"$set": document},
        upsert=True
    )

    # 모든 장소 정보를 하나의 큰 문자열로 결합
    formatted_results_str = "\n".join(formatted_results)

    return formatted_results_str

def just_chat(query: str):
    response = openai.ChatCompletion.create(
        model="gpt-4-0613",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": query}
        ]
    )
    return response.choices[0].message["content"]

def extractNumbers(text, userId, tripId):
    numbers = re.findall(r'\d+', text)
    indexes = [int(number) for number in numbers]

    return saveSelectedPlace(userId, tripId, indexes)

def saveSelectedPlace(userId, tripId, indexes):
    serp_collection = db['SerpData']
    save_place_collection = db['SavePlace']
    
    document = serp_collection.find_one({"userId": userId, "tripId": tripId})
    
    serp_data_length = len(document['data'])
    valid_indexes = [index-1 for index in indexes if 0 <= index-1 < serp_data_length]
    
    if not valid_indexes:
        print("No valid indexes found.")
        return
    
    selected_places = [document['data'][index] for index in valid_indexes]
    
    save_place_collection.update_one(
        {"userId": userId, "tripId": tripId},
        {"$push": {"placeData": {"$each": selected_places}}},
        upsert=True
    )
    
    return selected_places

def savePlans(userId, tripId):
    session = sqldb.sessionmaker()
    mytrip = session.query(myTrips).filter(myTrips.tripId == tripId).first()
    startDate = mytrip.startDate
    endDate = mytrip.endDate
    genai.configure(api_key=GEMINI_API_KEY)
    save_place_collection = db['SavePlace']
    document = save_place_collection.find_one({"userId": userId, "tripId": tripId})
    if not document:
        print("SavePlace에서 일치하는 문서를 찾을 수 없습니다.")
        return []
    place_data = document['placeData']
    place_data_str = json.dumps(place_data, ensure_ascii=False)
    model = genai.GenerativeModel('gemini-1.5-flash')
    query = f"""
    {startDate}부터 {endDate}까지 다음 장소들만 포함한 상세한 여행 일정을 만들어줘. {place_data_str} 데이터만을 모두 사용해서 각 날에 관광지, 레스토랑, 카페가 균형있게 포함되게 짜주고 되도록 경도와 위도가 가까운 장소들을 하루 일정에 적당히 넣어줘, 하루에 너무 많은 장소를 넣지는 말아줘 적당히 배분해 같은 장소는 일정을 여러번 넣지 않게 해줘. 되도록 식사시간 그니까 12시, 6시는 식당이나 카페에 방문하게 해주고 
    시간은 시작 시간만 HH:MM:SS 형태로 뽑아주고 날짜는 YYYY-MM-DD이렇게 뽑아줘 description 절대 생략하지 말고 다 넣어줘. title 은 장소에서 해야할 일을 알려주면 좋겠다 예를 들어 에펠탑 관광 이런식으로 만약에 데이터가 부족해서 전체 일정을 다 채우지 못한다 해도 괜찮아 그럼 그냥 아예 리턴을 하지마
    일정에 들어가야하는 정보는 다음과 같은 포맷으로 만들어줘: title: [title], date: [YYYY-MM-DD], time: [HH:MM:SS], place: [place], address: [address], latitude: [latitude], longitude: [longitude], description: [description]. 의 json배열로 뽑아줘
    date랑 time이 null이 아니라면 그 시간으로 일정을 짜줘
    """
    response = model.generate_content(query)

    cleaned_string = response.text.strip('```')
    cleaned_string= cleaned_string.replace('json', '').strip()
    datas = json.loads(cleaned_string)
    print(datas)

    for data in datas:
        new_trip = tripPlans(
            planId= str(uuid.uuid4()),
            userId= userId,
            tripId= tripId,
            title=data['title'],
            date=data['date'],
            time=data['time'],
            place=data['place'],
            address=data['address'],
            latitude=data['latitude'],
            longitude=data['longitude'],
            description=data['description']
        )
        session.add(new_trip)

    session.commit()

    save_place_collection.delete_one({"userId": userId, "tripId": tripId})
    session.close()

    query = f"""
    {cleaned_string}이걸 상세하게 설명해서 답변해줘 챗봇이 일정을 만들어준 것처럼 예를 들어 바르셀로나 여행 일정을 완성했어요! 1일차 - 이런식으로
    """
    response = model.generate_content(query).text

    return response

def check_trip_plan(user_id: str, trip_title: str, plan_title: str, date: str):
    """Get the trip plan details and check if the given user_id, trip_title, date, plan_title match. And confirm with the user"""
    session = Session()

    try:
        # 날짜 형식 변환
        formatted_date = convert_date_format(date)
        
        # 해당 여행의 계획을 찾음
        trip = session.query(myTrips).filter_by(userId=user_id, title=trip_title).first()
        if not trip:
            return "Trip not found."

        plan = session.query(tripPlans).filter_by(userId=user_id, tripId=trip.tripId, date=formatted_date, title=plan_title).first()

        if plan:
            confirmation_message = (
                f"해당 계획을 수정하는 것이 맞나요?\n"
                f"여행명: {trip.title}\n"
                f"일정명: {plan.title}\n"
                f"날짜: {plan.date}\n"
                f"시간: {plan.time}\n"
                f"장소: {plan.place}\n"
            )
            return confirmation_message
        else:
            return "일치하는 일정을 찾지 못하였습니다. 기존 일정을 확인 후, 다시 말씀해주세요."
    except Exception as e:
        return f"An error occurred: {str(e)}"
    finally:
        session.close()

# 여행 계획을 수정하는 함수
def update_trip_plan(user_id: str, trip_title: str, date: str, plan_title: str, new_time: str):
    """Update the trip plan with the given user_id, trip_title, date, plan_title, and new_time."""
    session = Session()

    try:
        # 날짜 형식 변환
        formatted_date = convert_date_format(date)

        # 해당 여행의 계획을 찾음
        trip = session.query(myTrips).filter_by(userId=user_id, title=trip_title).first()
        if not trip:
            return "Trip not found."

        plan = session.query(tripPlans).filter_by(userId=user_id, tripId=trip.tripId, date=formatted_date, title=plan_title).first()
        if plan:
            # 계획 시간 업데이트
            plan.time = new_time
            session.commit()
            return "성공적으로 일정 시간이 수정되었습니다."
        else:
            return "일정을 수정하는 과정에서 문제가 발생했습니다. 다시 시도해주세요."
    except Exception as e:
        session.rollback()
        return f"An error occurred: {str(e)}"
    finally:
        session.close()