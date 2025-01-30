import json
import random
import time
import datetime
from shapely.geometry import Point, Polygon

from api import *


class UsersList:
    def __init__(self, user_count=5):
        self.users_count = user_count
        """
        Создаёт список пользователей:
         [{'id': 0, 'name': 'Test_0', 'email': 'testUser_0@test.com'}, {'id': 1, 'name': 'Test_1', 'email': 'testUser_1@test.com'}, ...]
        """
        self.users = []
    def sync(self):
        api_users = []
        for i in range(0,self.users_count):
            email = "testUser_" + str(i) + "@test.com"
            user_info = GetUserInfo(email)
            if user_info["status"] == "success":
                api_users.append(user_info["auth_user"])
            elif user_info["status"] == "error" and user_info["message"]["error"] == "user not found":
                RegisterClient(email, "Test"+str(i))
                api_users.append(GetUserInfo(email)["auth_user"])
            else:
                raise Exception(json.dumps(user_info, indent=4, ensure_ascii=False))

        api_users = [{
            "id": user["u_id"],
            "name": user["u_name"],
            "email": user["u_email"],
        } for user in api_users]
        self.users = api_users
        print("API->Users synced")


    def get_users(self):
        """Возвращает полный список пользователей."""
        return self.users

    def get_user_ids(self):
        """Возвращает список всех id пользователей."""
        return [u['id'] for u in self.users]


class TaxiOrderSimulator:
    def __init__(
            self,
            polygon_coords,
            users_list,
            # --- Частоты появления (количество заказов в час для каждого типа) ---
            regular_frequency=2,  # Обычные заказы
            voting_frequency=1,  # Голосование
            # --- Время жизни ---
            regular_lifetime_minutes=10,  # Постоянное время жизни для обычных заказов
            voting_lifetime_minutes_min=5,  # Минимальное время жизни для "голосования"
            voting_lifetime_minutes_max=15,  # Максимальное время жизни для "голосования"
            # --- Геометрические параметры ---
            distance_min=0.01,  # Минимальное расстояние (в градусах)
            distance_max=0.05,  # Максимальное расстояние (в градусах)
            # --- Прочие параметры ---
            time_compression=1.0,  # Коэффициент сжатия времени
            simulation_hours=2,  # Длительность симуляции в часах (от 8:00)
            time_shift_minutes = 0
    ):
        """
        :param polygon_coords: список кортежей (lat, lon), не меньше 3 точек (многоугольник).
        :param users_list: экземпляр класса UsersList (список пользователей).
        :param regular_frequency: частота появления обычных заказов (шт/час).
        :param voting_frequency: частота появления заказов-голосований (шт/час).
        :param regular_lifetime_minutes: время жизни обычного заказа (минуты).
        :param voting_lifetime_minutes_min: минимальное время жизни "голосования" (минуты).
        :param voting_lifetime_minutes_max: максимальное время жизни "голосования" (минуты).
        :param distance_min: минимальное расстояние между точками отправления и назначения (в градусах).
        :param distance_max: максимальное расстояние между точками отправления и назначения (в градусах).
        :param time_compression: коэффициент сжатия времени (1.0 — без изменений).
        :param simulation_hours: длительность симуляции в часах, начиная с 8:00.

        ВАЖНО: Расстояния в Shapely рассчитываются в тех же единицах, что и координаты.
               Для координат (широта/долгота) это градусы, что не эквивалентно реальным метрам.
               Для точных геодезических расстояний используйте проекцию (pyproj) или иные методы.
        """
        # === Параметры, связанные с типами заказов ===
        self.regular_frequency = regular_frequency
        self.voting_frequency = voting_frequency
        self.regular_lifetime_minutes = regular_lifetime_minutes
        self.voting_lifetime_minutes_min = voting_lifetime_minutes_min
        self.voting_lifetime_minutes_max = voting_lifetime_minutes_max

        # === Геометрические параметры ===
        self.distance_min = distance_min
        self.distance_max = distance_max

        # === Прочие ===
        self.polygon = Polygon(polygon_coords)
        self.users_list = users_list
        self.time_compression = time_compression
        self.simulation_hours = simulation_hours

        # === Время старта симуляции (реальное) ===
        self.real_start_time = None

        # "Игровое" время начала — условно 8:00 сегодня
        self.sim_start_game_time = datetime.datetime.combine(
            datetime.date.today(),
            datetime.time(hour=8, minute=0, second=0)
        )

        # Список активных заказов
        self.active_orders = []

        # Расчёт игровых интервалов для каждого типа заказа
        # (сколько игровых секунд между двумя заказами данного типа)
        self.game_interval_between_regular = 3600 / self.regular_frequency if self.regular_frequency > 0 else float(
            'inf')
        self.game_interval_between_voting = 3600 / self.voting_frequency if self.voting_frequency > 0 else float('inf')

        # Отслеживание времени следующей генерации (в "игровых" секундах)
        self.next_generation_time_regular = 0.0
        self.next_generation_time_voting = 0.0

        self.time_shift_minutes = time_shift_minutes

    # ---------------------------------
    #   Вспомогательные методы
    # ---------------------------------
    def _random_point_in_polygon(self):
        """
        Генерирует случайную точку внутри полигона методом "bounding box + проверка".
        """
        minx, miny, maxx, maxy = self.polygon.bounds
        while True:
            rand_x = random.uniform(minx, maxx)
            rand_y = random.uniform(miny, maxy)
            point = Point(rand_x, rand_y)
            if self.polygon.contains(point):
                return (rand_x, rand_y)

    def _random_dest_in_polygon_within_dist_range(self, origin, dmin, dmax):
        """
        Генерирует случайную точку внутри полигона,
        чтобы расстояние от origin до этой точки лежало в [dmin, dmax].
        """
        origin_point = Point(origin)
        while True:
            dest = self._random_point_in_polygon()
            distance = origin_point.distance(Point(dest))
            if dmin <= distance <= dmax:
                return dest

    def _get_game_time_since_start(self):
        """
        Сколько "игровых" секунд прошло с момента старта симуляции (учитывая time_compression).
        """
        if self.real_start_time is None:
            return 0.0
        real_elapsed = time.time() - self.real_start_time
        game_elapsed = real_elapsed * self.time_compression
        return game_elapsed

    def _get_current_game_datetime(self):
        """
        Текущее "игровое" datetime (8:00 + прошедшие "игровые" секунды).
        """
        elapsed_seconds = self._get_game_time_since_start()
        return self.sim_start_game_time + datetime.timedelta(seconds=elapsed_seconds)

    def _get_free_user_ids(self):
        """
        Возвращает список id пользователей, у которых на данный момент нет активных заказов.
        """
        used_user_ids = {order['userID'] for order in self.active_orders}
        all_ids = self.users_list.get_user_ids()
        free_user_ids = [uid for uid in all_ids if uid not in used_user_ids]
        return free_user_ids

    # ---------------------------------
    #   Генерация заказов
    # ---------------------------------
    def _generate_regular_order(self):
        """
        Генерирует Обычный заказ (regular order).
        Если нет свободных пользователей, заказ не создаётся.
        """
        free_users = self._get_free_user_ids()
        if not free_users:
            # Нет свободных пользователей — пропускаем
            return

        chosen_user_id = random.choice(free_users)

        origin_coords = self._random_point_in_polygon()
        destination_coords = self._random_dest_in_polygon_within_dist_range(
            origin_coords,
            self.distance_min,
            self.distance_max
        )

        creation_time = self._get_current_game_datetime()
        expire_time = creation_time + datetime.timedelta(minutes=self.regular_lifetime_minutes)

        time_shift = ("0"*(2-len(str(self.time_shift_minutes//60).replace("-",""))) + str(self.time_shift_minutes//60).replace("-","")
                      + ":" + "0"*(2-len(str(self.time_shift_minutes%60).replace("-",""))) + str(self.time_shift_minutes%60).replace("-",""))
        time_shift_delimeter = "+"
        if self.time_shift_minutes < 0:
            time_shift_delimeter = "-"
        response = CreateDrive(chosen_user_id,
                               origin_coords[0],
                               origin_coords[1],
                               destination_coords[0],
                               destination_coords[1],
                               creation_time.strftime("%Y-%m-%d %H:%M:%S") + time_shift_delimeter + time_shift,
                               self.regular_lifetime_minutes*60,
                               1,
                               []) # Для обычного заказа b_services = []
        print(
            "API->Order " + str(response["data"]["b_id"]) + " created. Type: regular, Start time: " + creation_time.strftime(
                "%Y-%m-%d %H:%M:%S") + time_shift_delimeter + time_shift)
        #print(json.dumps(response, indent=4))
        #print(json.dumps(make_request(url_prefix + "drive/get/" + str(response["data"]["b_id"]),{"token": GetAdminHashAndToken()[0],"u_hash": GetAdminHashAndToken()[1]}), indent=4))
        order = {
            'id': response["data"]["b_id"],
            'order_type': 'regular',
            'name': 'order',
            'userID': chosen_user_id,
            'coords': origin_coords,
            'destination_coords': destination_coords,
            'creation_time': creation_time,
            'expire_time': expire_time
        }
        self.active_orders.append(order)

    def _generate_voting_order(self):
        """
        Генерирует заказ-голосование (voting order) с временем жизни
        в диапазоне [voting_lifetime_minutes_min, voting_lifetime_minutes_max].
        """
        free_users = self._get_free_user_ids()
        if not free_users:
            # Нет свободных пользователей — пропускаем
            return

        chosen_user_id = random.choice(free_users)

        origin_coords = self._random_point_in_polygon()
        destination_coords = self._random_dest_in_polygon_within_dist_range(
            origin_coords,
            self.distance_min,
            self.distance_max
        )

        creation_time = self._get_current_game_datetime()

        # Случайная длительность "голосования" (мин)
        voting_lifetime = random.randint(self.voting_lifetime_minutes_min,
                                         self.voting_lifetime_minutes_max)

        expire_time = creation_time + datetime.timedelta(minutes=voting_lifetime)

        time_shift = ("0" * (2 - len(str(self.time_shift_minutes // 60).replace("-", ""))) + str(
            self.time_shift_minutes // 60).replace("-", "")
                      + ":" + "0" * (2 - len(str(self.time_shift_minutes % 60).replace("-", ""))) + str(
                    self.time_shift_minutes % 60).replace("-", ""))
        time_shift = time_shift.replace("-", "")
        time_shift_delimeter = "+"
        if self.time_shift_minutes < 0:
            time_shift_delimeter = "-"
        response = CreateDrive(chosen_user_id,
                               origin_coords[0],
                               origin_coords[1],
                               destination_coords[0],
                               destination_coords[1],
                               creation_time.strftime("%Y-%m-%d %H:%M:%S") + time_shift_delimeter + time_shift,
                               voting_lifetime*60,
                               1,
                               ['5'])  # Для voting b_services = ['5']
        print("API->Order " + str(response["data"]["b_id"]) + " created. Type: voting, Start time: " + creation_time.strftime("%Y-%m-%d %H:%M:%S") + time_shift_delimeter + time_shift)

        order = {
            'id': response["data"]["b_id"],
            'order_type': 'voting',
            'name': 'Vote',
            'userID': chosen_user_id,
            'coords': origin_coords,
            'destination_coords': destination_coords,
            'creation_time': creation_time,
            'expire_time': expire_time
        }
        self.active_orders.append(order)

    # ---------------------------------
    #   Основные методы симуляции
    # ---------------------------------
    def _remove_expired_orders(self):
        """
        Удаляем заказы, у которых истекло время жизни.
        """
        now = self._get_current_game_datetime()

        expired_orders = [
            o for o in self.active_orders
            if o['expire_time'] <= now
        ]
        for order in expired_orders:
            print(f"API->Order {order['id']} expired")
            CancelDrive(order['id'], "Order expired")

        self.active_orders = [
            o for o in self.active_orders
            if o['expire_time'] > now
        ]

    def start(self):
        """
        Запускаем симуляцию (фиксируем реальное время).
        """
        self.real_start_time = time.time()

    def update(self):
        """
        Обновляет состояние симуляции:
         - Генерирует обычные заказы, если пришло время (и есть свободные пользователи).
         - Генерирует заказы-голосования, если пришло время (и есть свободные пользователи).
         - Удаляет просроченные заказы.
         - Проверяет окончание симуляции (необязательно останавливать).
        """
        if self.real_start_time is None:
            return  # Симуляция ещё не запущена

        current_game_time = self._get_game_time_since_start()

        # --- Генерация обычных заказов ---
        while current_game_time >= self.next_generation_time_regular:
            self._generate_regular_order()
            self.next_generation_time_regular += self.game_interval_between_regular

        # --- Генерация заказов-голосований ---
        while current_game_time >= self.next_generation_time_voting:
            self._generate_voting_order()
            self.next_generation_time_voting += self.game_interval_between_voting

        # --- Удаляем "протухшие" заказы ---
        self._remove_expired_orders()

        # --- (Опционально) проверяем окончание симуляции ---
        end_game_time = self.sim_start_game_time + datetime.timedelta(hours=self.simulation_hours)
        if self._get_current_game_datetime() >= end_game_time:
            # Здесь можно завершать/останавливать, если нужно
            pass

    def get_active_orders(self):
        """
        Возвращает список активных заказов в формате:
        {
            'order_type': 'regular' или 'voting',
            'name': 'Простой заказ' или 'Голосование',
            'userID': <int>,
            'coords': (lat, lon),
            'destination_coords': (lat, lon),
            'creation_time': 'HH:MM:SS',
            'remaining_lifetime': 'X мин Y сек'
        }
        """
        now = self._get_current_game_datetime()
        result = []
        for o in self.active_orders:
            remaining_seconds = (o['expire_time'] - now).total_seconds()
            creation_time_str = o['creation_time'].strftime('%H:%M:%S')
            result.append({
                'userID': o['userID'],
                'coords': o['coords'],
                'destination_coords': o['destination_coords'],
                'creation_time': creation_time_str,
                'remaining_lifetime': f"{int(remaining_seconds // 60)} мин {int(remaining_seconds % 60)} сек"
            })
        return result


if __name__ == '__main__':
    # Пример использования

    # Создаём список пользователей (5 пользователей)
    users = UsersList(user_count=5)
    users.sync()

    # Координаты полигона (широта, долгота):
    polygon_coords = [
        (30.42854544631636, -9.611663818359375),
        (30.45459295698008, -9.53819274902344),
        (30.420256142845158, -9.545745849609377),
        (30.410189613309132, -9.526519775390627),
        (30.385314913418373, -9.482574462890627),
        (30.35806392728733, -9.477081298828127),
        (30.34325042354528, -9.472961425781252),
        (30.329620019722665, -9.481201171875002),
        (30.315987718557867, -9.50798034667969),
        (30.329620019722665, -9.539566040039064),
        (30.347990988731844, -9.567718505859377),
        (30.378206692827195, -9.602050781250002),
        (30.42854544631636, -9.611663818359375)
    ]

    # Создаём симулятор
    # Частоты:
    #   regular_frequency=5  -> 5 обычных заказов в час
    #   voting_frequency=2   -> 2 заказа-голосования в час
    simulator = TaxiOrderSimulator(
        polygon_coords=polygon_coords,
        users_list=users,
        regular_frequency=5,
        voting_frequency=2,
        regular_lifetime_minutes=10,
        voting_lifetime_minutes_min=5,
        voting_lifetime_minutes_max=15,
        distance_min=0.01,
        distance_max=0.05,
        time_compression=15.0,  # ускоряем время в 20 раз
        simulation_hours=4,  # 1 час симуляции (с 8:00 до 9:00)
        time_shift_minutes=3*60
    )

    simulator.start()

    # ---------------------------------------------
    #  Рассчитываем, сколько реального времени
    #  займёт simulation_hours виртуального времени
    # ---------------------------------------------
    # Сколько всего "игровых" (виртуальных) секунд:
    total_game_seconds = simulator.simulation_hours * 3600
    # Сколько это в реальных секундах с учётом time_compression:
    total_real_seconds = total_game_seconds / simulator.time_compression

    # Таким образом, мы можем ждать ровно total_real_seconds
    end_time = time.time() + total_real_seconds

    # Запускаем цикл:
    while time.time() < end_time:
        simulator.update()

        # (Опционально) смотрим активные заказы
        active_orders = simulator.get_active_orders()
        for order in active_orders:
            print(" ", order)

        # Небольшая пауза, чтобы не «забить» консоль
        time.sleep(2)

    # Дополнительный вызов update() — если хотим «доубирать» заказы и отменить их на API
    simulator.update()

