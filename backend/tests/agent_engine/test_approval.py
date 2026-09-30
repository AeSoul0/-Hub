"""
@file backend/tests/agent_engine/test_approval.py
@description Unit tests for ApprovalManager.
"""
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
import json
import hashlib
from app.agent_engine.approval.manager import ApprovalManager
from app.domain.models.audit import ApprovalRecord

@pytest.mark.anyio
@patch('app.agent_engine.approval.manager.SessionLocal')
async def test_check_approval_status_none(mock_session_local):
    mock_db = MagicMock()
    mock_session_local.return_value.__enter__.return_value = mock_db
    
    mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
    
    status = await ApprovalManager.check_approval_status("session_1", "tool_a", {"a": 1})
    assert status == "NONE"

@pytest.mark.anyio
@patch('app.agent_engine.approval.manager.SessionLocal')
async def test_check_approval_status_expired(mock_session_local):
    mock_db = MagicMock()
    mock_session_local.return_value.__enter__.return_value = mock_db
    
    record = ApprovalRecord(expires_at=datetime.utcnow() - timedelta(hours=1))
    mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = record
    
    status = await ApprovalManager.check_approval_status("session_1", "tool_a", {"a": 1})
    assert status == "EXPIRED"

@pytest.mark.anyio
@patch('app.agent_engine.approval.manager.SessionLocal')
async def test_check_approval_status_approved(mock_session_local):
    mock_db = MagicMock()
    mock_session_local.return_value.__enter__.return_value = mock_db
    
    record = ApprovalRecord(expires_at=datetime.utcnow() + timedelta(hours=1), decision="ALLOW")
    mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = record
    
    status = await ApprovalManager.check_approval_status("session_1", "tool_a", {"a": 1})
    assert status == "APPROVED"

@pytest.mark.anyio
@patch('app.agent_engine.approval.manager.SessionLocal')
async def test_request_approval(mock_session_local):
    mock_db = MagicMock()
    mock_session_local.return_value.__enter__.return_value = mock_db
    
    req_id = await ApprovalManager.request_approval("session_1", "tool_a", {"a": 1})
    
    mock_db.add.assert_called_once()
    mock_db.commit.assert_called_once()

@pytest.mark.anyio
@patch('app.agent_engine.approval.manager.SessionLocal')
async def test_grant_approval(mock_session_local):
    mock_db = MagicMock()
    mock_session_local.return_value.__enter__.return_value = mock_db
    
    record = ApprovalRecord(id="req_123")
    mock_db.query.return_value.filter.return_value.first.return_value = record
    
    await ApprovalManager.grant_approval("req_123", "ALLOW")
    
    assert record.decision == "ALLOW"
    assert record.decided_by == "admin"
    mock_db.commit.assert_called_once()
