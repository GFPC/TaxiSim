import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from shapely.geometry import Point, Polygon


def visualize_simulation(simulator):
    """
    Визуализация симуляции в режиме анимации (matplotlib).
    Предполагается, что simulator уже создан и запущен (simulator.start()).
    """
    fig, ax = plt.subplots()

    x_poly, y_poly = simulator.polygon.exterior.xy
    ax.fill(x_poly, y_poly, alpha=0.2, edgecolor='black', linewidth=1)

    points_plot = ax.scatter([], [], color='red', marker='o')

    def init():
        ax.set_title("Taxi Orders Simulation")
        ax.set_xlabel("Долгота (x)")
        ax.set_ylabel("Широта (y)")
        return (points_plot,)

    def update(frame):
        # Обновляем симуляцию
        simulator.update()
        orders = simulator.get_active_orders()

        # Извлекаем координаты активных заказов
        xs = [o['coords'][0] for o in orders]
        ys = [o['coords'][1] for o in orders]

        # Обновляем scatter plot
        points_plot.set_offsets(list(zip(xs, ys)))

        # Можно также отобразить текущее "игровое" время
        current_game_dt = simulator._get_current_game_datetime()
        ax.set_title(f"Taxi Orders Simulation — {current_game_dt.strftime('%H:%M:%S')}")

        return (points_plot,)

    anim = FuncAnimation(fig, update, init_func=init, interval=1000, blit=False, frames=100)
    plt.show()


if __name__ == '__main__':
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

    from main import TaxiOrderSimulator,UsersList
    users = UsersList(user_count=5)
    users.sync()

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
        time_shift_minutes=3 * 60
    )
    simulator.start()

    visualize_simulation(simulator)
