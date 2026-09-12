"""
Test that sessions survive Cloud Run revision deployments.

This test verifies that:
1. Sessions are stored in Firestore (not in-memory)
2. Sessions persist across application restarts
3. Session data remains intact after redeploy
"""
import pytest

from app.core.firestore import firestore_manager


@pytest.mark.asyncio
async def test_session_persistence_in_firestore():
    """Test that sessions are stored in Firestore and persist."""
    # Initialize Firestore (use emulator in test)
    firestore_manager.initialize(use_emulator=True)

    # Create a test session
    session_id = "test-session-survival-123"
    user_id = "test-user-123"
    email = "test@example.com"

    session_data = await firestore_manager.create_session(
        session_id=session_id,
        user_id=user_id,
        email=email,
        expires_in_days=1,
        metadata={"test": "data"}
    )

    # Verify session was created
    assert session_data["session_id"] == session_id
    assert session_data["user_id"] == user_id
    assert session_data["email"] == email
    assert session_data["is_active"] is True

    # Retrieve the session
    retrieved = await firestore_manager.get_session(session_id)
    assert retrieved is not None
    assert retrieved["user_id"] == user_id
    assert retrieved["email"] == email
    assert retrieved["is_active"] is True
    assert retrieved["metadata"]["test"] == "data"

    # Simulate application restart by reinitializing Firestore
    firestore_manager._client = None
    firestore_manager.initialize(use_emulator=True)

    # Session should still be retrievable after restart
    retrieved_after_restart = await firestore_manager.get_session(session_id)
    assert retrieved_after_restart is not None
    assert retrieved_after_restart["user_id"] == user_id
    assert retrieved_after_restart["email"] == email

    # Cleanup
    await firestore_manager.delete_session(session_id)


@pytest.mark.asyncio
async def test_session_expiration_handling():
    """Test that expired sessions are properly handled."""
    firestore_manager.initialize(use_emulator=True)

    # Create a session
    session_id = "test-expired-session-456"
    user_id = "test-user-456"
    email = "test2@example.com"

    await firestore_manager.create_session(
        session_id=session_id,
        user_id=user_id,
        email=email,
        expires_in_days=1,
        metadata={"test": "expired"}
    )

    # Verify session is active
    retrieved = await firestore_manager.get_session(session_id)
    assert retrieved is not None
    assert retrieved["is_active"] is True

    # Deactivate the session
    await firestore_manager.update_session(session_id, {"is_active": False})

    # Attempt to retrieve deactivated session should return None
    retrieved = await firestore_manager.get_session(session_id)
    assert retrieved is None, "Deactivated session should return None"

    # Note: Skip cleanup if emulator connection fails
    try:
        await firestore_manager._client.collection("sessions").document(session_id).delete()
    except Exception:
        pass  # Cleanup failed, but test passed


@pytest.mark.asyncio
async def test_multiple_sessions_per_user():
    """Test that a user can have multiple active sessions."""
    firestore_manager.initialize(use_emulator=True)

    user_id = "test-user-multi-789"
    email = "multi@example.com"

    # Create multiple sessions for the same user
    session_ids = []
    for i in range(3):
        session_id = f"test-session-{user_id}-{i}"
        session_ids.append(session_id)
        await firestore_manager.create_session(
            session_id=session_id,
            user_id=user_id,
            email=email,
            expires_in_days=1
        )

    # All sessions should be retrievable
    for session_id in session_ids:
        retrieved = await firestore_manager.get_session(session_id)
        assert retrieved is not None
        assert retrieved["user_id"] == user_id

    # Delete all sessions for the user
    deleted_count = await firestore_manager.delete_user_sessions(user_id)
    assert deleted_count == 3

    # Verify all sessions are deleted
    for session_id in session_ids:
        retrieved = await firestore_manager.get_session(session_id)
        assert retrieved is None
