"""Tests for users routes and profile update service."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from auth.models import User
from tests.conftest import make_client


@pytest.mark.asyncio
async def test_get_profile_returns_user_data(db: AsyncSession, mock_user: User):
    async with make_client(mock_user, db) as client:
        response = await client.get("/users/me")

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_profile_correct_fields(db: AsyncSession, mock_user: User):
    async with make_client(mock_user, db) as client:
        response = await client.get("/users/me")

    data = response.json()
    assert "id" in data
    assert "email" in data
    assert "name" in data
    assert "daily_goal" in data
    assert "streak_count" in data
    assert "ai_configured" in data


@pytest.mark.asyncio
async def test_get_profile_values_match_user(db: AsyncSession, mock_user: User):
    async with make_client(mock_user, db) as client:
        response = await client.get("/users/me")

    data = response.json()
    assert data["email"] == mock_user.email
    assert data["daily_goal"] == mock_user.daily_goal
    assert data["streak_count"] == mock_user.streak_count


@pytest.mark.asyncio
async def test_update_profile_name(db: AsyncSession, mock_user: User):
    async with make_client(mock_user, db) as client:
        response = await client.patch("/users/me", json={"name": "Alice"})

    assert response.status_code == 200
    await db.refresh(mock_user)
    assert mock_user.name == "Alice"


@pytest.mark.asyncio
async def test_update_profile_name_empty_string_rejected(db: AsyncSession, mock_user: User):
    async with make_client(mock_user, db) as client:
        response = await client.patch("/users/me", json={"name": ""})

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_update_profile_name_whitespace_only_rejected(db: AsyncSession, mock_user: User):
    async with make_client(mock_user, db) as client:
        response = await client.patch("/users/me", json={"name": "   "})

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_update_profile_name_too_long_rejected(db: AsyncSession, mock_user: User):
    async with make_client(mock_user, db) as client:
        response = await client.patch("/users/me", json={"name": "x" * 256})

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_update_profile_daily_goal_valid(db: AsyncSession, mock_user: User):
    async with make_client(mock_user, db) as client:
        response = await client.patch("/users/me", json={"daily_goal": 10})

    assert response.status_code == 200
    await db.refresh(mock_user)
    assert mock_user.daily_goal == 10


@pytest.mark.asyncio
async def test_update_profile_daily_goal_minimum(db: AsyncSession, mock_user: User):
    async with make_client(mock_user, db) as client:
        response = await client.patch("/users/me", json={"daily_goal": 1})

    assert response.status_code == 200
    await db.refresh(mock_user)
    assert mock_user.daily_goal == 1


@pytest.mark.asyncio
async def test_update_profile_daily_goal_maximum(db: AsyncSession, mock_user: User):
    async with make_client(mock_user, db) as client:
        response = await client.patch("/users/me", json={"daily_goal": 50})

    assert response.status_code == 200
    await db.refresh(mock_user)
    assert mock_user.daily_goal == 50


@pytest.mark.asyncio
async def test_update_profile_daily_goal_zero(db: AsyncSession, mock_user: User):
    async with make_client(mock_user, db) as client:
        response = await client.patch("/users/me", json={"daily_goal": 0})

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_update_profile_daily_goal_too_high(db: AsyncSession, mock_user: User):
    async with make_client(mock_user, db) as client:
        response = await client.patch("/users/me", json={"daily_goal": 51})

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_update_profile_daily_goal_negative(db: AsyncSession, mock_user: User):
    async with make_client(mock_user, db) as client:
        response = await client.patch("/users/me", json={"daily_goal": -1})

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_update_profile_partial_only_changes_target_field(db: AsyncSession, mock_user: User):
    original_goal = mock_user.daily_goal
    original_email = mock_user.email

    async with make_client(mock_user, db) as client:
        response = await client.patch("/users/me", json={"name": "Bob"})

    assert response.status_code == 200
    await db.refresh(mock_user)
    assert mock_user.name == "Bob"
    assert mock_user.daily_goal == original_goal      # unchanged
    assert mock_user.email == original_email  # unchanged


@pytest.mark.asyncio
async def test_update_profile_empty_body_returns_success(db: AsyncSession, mock_user: User):
    original_goal = mock_user.daily_goal

    async with make_client(mock_user, db) as client:
        response = await client.patch("/users/me", json={})

    assert response.status_code == 200
    assert response.json()["message"] == "Profile updated successfully"
    await db.refresh(mock_user)
    assert mock_user.daily_goal == original_goal  # nothing changed


@pytest.mark.asyncio
async def test_update_profile_multiple_fields_at_once(db: AsyncSession, mock_user: User):
    async with make_client(mock_user, db) as client:
        response = await client.patch(
            "/users/me",
            json={"name": "Carol", "daily_goal": 8},
        )

    assert response.status_code == 200
    await db.refresh(mock_user)
    assert mock_user.name == "Carol"
    assert mock_user.daily_goal == 8


@pytest.mark.asyncio
async def test_update_profile_success_message(db: AsyncSession, mock_user: User):
    async with make_client(mock_user, db) as client:
        response = await client.patch("/users/me", json={"name": "Dave"})

    assert response.json()["message"] == "Profile updated successfully"
