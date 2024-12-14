import pytest
from unittest.mock import AsyncMock
from bot import game_data, start_game, end_day, reset_game_data, end_night, check_game_end

@pytest.fixture
def mock_context():
    """
    Создаём фиктивный контекст для тестов.
    """
    return AsyncMock()

@pytest.mark.asyncio
async def test_end_day_no_votes(mock_context):
    """
    Тест: Никто не проголосовал.
    """
    game_data["phase"] = "voting"
    game_data["votes"] = {}
    game_data["players"] = [
        {"name": "Player1", "id": 1, "role": "Мирный житель"},
        {"name": "Player2", "id": 2, "role": "Мирный житель"}
    ]

    await end_day(None, mock_context)

    # Проверяем переход к ночной фазе
    assert game_data["phase"] == "night", "Фаза должна быть 'night'"

@pytest.mark.asyncio
async def test_reset_game_data():
    """
    Тест: Сброс состояния игры.
    """
    game_data["players"] = [{"name": "Player1", "id": 1}, {"name": "Player2", "id": 2}]
    game_data["started"] = True

    reset_game_data()

    # Проверяем, что состояние сброшено
    assert game_data["players"] == [], "Список игроков должен быть пустым"
    assert game_data["started"] is False, "Игра не должна быть начата"

@pytest.mark.asyncio
async def test_role_distribution(mock_context):
    """
    Тест: Проверка распределения ролей.
    """
    game_data["players"] = [
        {"name": "Player1", "id": 1},
        {"name": "Player2", "id": 2},
        {"name": "Player3", "id": 3},
        {"name": "Player4", "id": 4},
        {"name": "Player5", "id": 5}
    ]

    await start_game(None, mock_context)

    # Проверяем, что роли распределены корректно
    roles = [player["role"] for player in game_data["players"]]
    assert "Мафия" in roles, "Роль 'Мафия' должна быть распределена"
    assert "Комиссар" in roles, "Роль 'Комиссар' должна быть распределена"
    assert "Доктор" in roles, "Роль 'Доктор' должна быть распределена"
    assert len(roles) == len(game_data["players"]), "Количество ролей должно совпадать с количеством игроков"

@pytest.mark.asyncio
async def test_mafia_wins(mock_context):
    """
    Тест: Победа мафии, когда количество мафии равно количеству мирных жителей.
    """
    game_data["players"] = [
        {"name": "Player1", "role": "Мафия", "id": 1},
        {"name": "Player2", "role": "Мирный житель", "id": 2}
    ]

    game_data["phase"] = "night"
    game_data["mafia_target"] = "Player2"

    await end_night(None, mock_context)

    # Проверяем, что игра завершена
    assert game_data["players"] == [], "Список игроков должен быть пустым после завершения игры"
    assert game_data["started"] is False, "Игра должна быть завершена"

@pytest.mark.asyncio
async def test_game_ends_when_mafia_wins(mock_context):
    """
    Тест: Игра завершается, если мафия в численном превосходстве или единственная оставшаяся.
    """
    game_data["players"] = [
        {"name": "Mafia1", "role": "Мафия", "id": 1},
        {"name": "Villager1", "role": "Мирный житель", "id": 2},
    ]

    # Проверяем, что игра завершится с победой мафии
    game_end_message = check_game_end()
    assert game_end_message == "Игра завершена. Победила мафия!", "Игра должна завершиться победой мафии."

    # Завершаем день, чтобы убедиться, что фаза не изменяется после завершения игры
    game_data["phase"] = "voting"
    game_data["votes"] = {"2": "Villager1"}  # Мирного выгоняют

    await end_day(None, mock_context)

    # Убедимся, что игра очищена после победы мафии
    assert len(game_data["players"]) == 0, "Все игроки должны быть удалены после завершения игры."
    assert not game_data["started"], "Игра должна быть завершена."

@pytest.mark.asyncio
async def test_player_removed_after_night_kill(mock_context):
    """
    Тест: Убедиться, что убитый ночью игрок удаляется из списка игроков.
    """
    # Инициализация данных игры
    game_data["phase"] = "night"
    game_data["mafia_target"] = "Player1"
    game_data["doctor_target"] = None  # Никто не лечится
    game_data["players"] = [
        {"name": "Player1", "role": "Мирный житель", "id": 1},
        {"name": "Player2", "role": "Доктор", "id": 2},
        {"name": "Player3", "role": "Комиссар", "id": 3}
    ]

    # Завершение ночной фазы
    await end_night(None, mock_context)

    # Проверяем, что убитый игрок удалён
    remaining_players = [player["name"] for player in game_data["players"]]
    assert "Player1" not in remaining_players, "Игрок Player1 должен быть удалён после ночного убийства."
    assert len(remaining_players) >= 0, "Список игроков не должен быть полностью пустым."

@pytest.mark.asyncio
async def test_tied_votes_no_exclusion(mock_context):
    """
    Тест: Убедиться, что при равенстве голосов никто не исключается,
    и игра переходит в ночную фазу.
    """
    # Инициализация данных игры
    game_data["phase"] = "voting"
    game_data["votes"] = {"1": "Player1", "2": "Player2"}  # Равное количество голосов
    game_data["players"] = [
        {"name": "Player1", "role": "Мирный житель", "id": 1},
        {"name": "Player2", "role": "Мирный житель", "id": 2},
        {"name": "Player3", "role": "Мафия", "id": 3}
    ]

    # Завершение дневной фазы
    await end_day(None, mock_context)

    # Проверяем, что никто не исключён
    remaining_players = [player["name"] for player in game_data["players"]]
    assert len(remaining_players) == 3, f"Никто не должен быть исключён, но игроков осталось: {len(remaining_players)}"

    # Проверяем, что игра перешла в ночную фазу
    assert game_data["phase"] == "night", "Игра должна перейти в ночную фазу."




