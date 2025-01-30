import hashlib
from urllib.parse import urlencode,unquote
import requests
import json

ADMIN_CREDENTIALS_FILE = "gruzvill_admin.txt"

url_prefix = "https://ibronevik.ru/taxi/c/gruzvill/api/v1/"
bot_admin_login = "admin@ibronevik.ru"
bot_admin_password = "p@ssw0rd"
bot_admin_type = "e-mail"

# make_request осуществляет запросы к апи с автоподстановкой заголовков
def make_request(url, data={}, method="POST"):
    req = None
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json"
    }
    if method == "POST":
        req = requests.post(url, data=urlencode(data), headers=headers)
    elif method == "GET":
        req = requests.get(url, data=urlencode(data), headers=headers)
    data = json.loads(unquote(req.text))
    if req.status_code != 200:
        print("REQUESTS ERROR: " + str(data["code"]))
    return data

# GetAdminHashAndToken получает хэш админа и токен и хранит их в указанном файле(создается если его нет)
# это сделано для сокращения времени запросов, требующих авторизации админа
# token и u_hash не меняются во время работы
def GetAdminHashAndToken():
    try:
        f = open(ADMIN_CREDENTIALS_FILE, "x")
        f.close()
    except:
        pass
    f = open(ADMIN_CREDENTIALS_FILE, "r+")
    r = f.read().split("\n")
    if len(r) == 1 or len(r) == 0:
        data = {
            "login": bot_admin_login,
            "password": bot_admin_password,
            "type": bot_admin_type
        }
        data = make_request(url_prefix + "auth", data)
        AUTH_HASH = data["auth_hash"]
        data = {
            "auth_hash": AUTH_HASH
        }
        data = make_request(url_prefix + "token", data)
        TOKEN = data["data"]["token"]
        U_HASH = data["data"]["u_hash"]
        f.write(TOKEN + "\n" + U_HASH)
        f.close()
        return [TOKEN, U_HASH]
    elif len(r) == 2:
        TOKEN = r[0]
        U_HASH = r[1]
        return [TOKEN, U_HASH]

# Возвращает token и u_hash пользователя, а также данные о пользователе
def GetUserInfo(email:str):
    token_and_hash = GetAdminHashAndToken()
    data = {
        "token": token_and_hash[0],
        "u_hash": token_and_hash[1],
        "u_a_email": email,
    }
    data = make_request(url_prefix + "token", data=data)
    return data
def RegisterClient(email:str, name):
    token_and_hash = GetAdminHashAndToken()
    data = {
        "token": token_and_hash[0],
        "u_hash": token_and_hash[1],
        "u_name": name,
        "u_email": email,
        "u_role": "2",
        "st": ""
    }
    data = make_request(url_prefix+"register",data=data,method="POST")
    return data
def CreateDrive(u_id,start_latitude,start_longitude,end_latitude,end_longitude,start_datetime,waiting,passenger_count=1,services=[]):
    token,u_hash = GetAdminHashAndToken()
    data = {
        "token": token,
        "u_hash": u_hash,

        "u_a_id":str(u_id), # Авторизован(по токену и хэшу) админ, а drive создастя от лица юзера - имиация пользователя админом
        "u_a_role":1,
        "u_check_state": 2,
        "data":json.dumps({
            "b_start_latitude": start_latitude,
            "b_start_longitude": start_longitude,
            "b_destination_latitude": end_latitude,
            "b_destination_longitude": end_longitude,
            "b_start_datetime": start_datetime,
            "b_max_waiting": waiting,
            "b_passengers_count": passenger_count,
            "b_payment_way": "1",
            "b_services": services
        })

    }
    data = make_request(url_prefix + "drive/", data=data)
    return data

def CancelDrive(drive_id,reason:str):
    token,u_hash = GetAdminHashAndToken()
    data = {
        "token": token,
        "u_hash": u_hash,

        "u_a_role":4, # user_role=4 for deleting drive under admin

        "action":"set_cancel_state",
        "reason":reason,
    }
    data = make_request(url_prefix + "drive/get/"+str(drive_id), data=data)
    return data
