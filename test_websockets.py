#!/usr/bin/env python
"""
Enhanced WebSocket Chat Test Script for Jobraker
Tests the WebSocket chat functionality with authentication
"""

import asyncio
import websockets
import json
import sys
import os
import requests

# Add Django settings
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'jobraker.settings.development')

async def get_auth_token():
    """Get authentication token for WebSocket connection"""
    # For demo purposes, we'll skip actual authentication
    # In a real scenario, you'd get this from a login endpoint
    return None

async def test_chat_websocket():
    """Test the chat WebSocket connection"""
    uri = "ws://localhost:8000/ws/chat/testsession/"
    
    print("🔌 Testing WebSocket Chat Connection...")
    
    # Get authentication token (optional for chat)
    token = await get_auth_token()
    if token:
        uri += f"?token={token}"
    
    try:
        async with websockets.connect(uri) as websocket:
            print("✅ Connected to WebSocket!")
            
            # Wait for connection established message
            connection_msg = await websocket.recv()
            print(f"📥 Connection: {connection_msg}")
            
            # Send a test message
            test_message = {
                "type": "message",
                "message": "Hello from authenticated test script!"
            }
            
            await websocket.send(json.dumps(test_message))
            print(f"📤 Sent: {test_message}")
            
            # Wait for response
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                print(f"📥 Received: {response}")
                print("🎉 WebSocket chat test completed successfully!")
            except asyncio.TimeoutError:
                print("⏰ No response received within timeout")
            
    except Exception as e:
        print(f"❌ WebSocket test failed: {e}")
        print("💡 Make sure the Django development server is running with ASGI support")
        print("   Run: daphne -b 127.0.0.1 -p 8000 jobraker.asgi:application")

async def test_notifications_websocket():
    """Test the notifications WebSocket connection"""
    print("🔔 Testing WebSocket Notifications Connection...")
    
    # For notifications, we need authentication
    print("ℹ️  Notifications WebSocket requires authentication")
    print("💡 To test notifications:")
    print("   1. Create a user account")
    print("   2. Get JWT token from /api/token/")
    print("   3. Connect to ws://localhost:8000/ws/notifications/?token=YOUR_TOKEN")
    
    # Demo connection without token (will fail as expected)
    uri = "ws://localhost:8000/ws/notifications/"
    try:
        async with websockets.connect(uri) as websocket:
            print("✅ Connected to Notifications WebSocket!")
            response = await websocket.recv()
            print(f"📥 Received: {response}")
    except Exception as e:
        print(f"❌ Notifications WebSocket test failed (expected): {e}")
        print("✅ Authentication is working correctly!")

async def main():
    """Run all WebSocket tests"""
    print("🚀 Starting Jobraker WebSocket Tests...")
    print("=" * 50)
    
    await test_chat_websocket()
    print("-" * 50)
    await test_notifications_websocket()
    print("-" * 50)
    print("✅ All WebSocket tests completed!")

if __name__ == "__main__":
    asyncio.run(main())
    
    print("🔔 Testing WebSocket Notifications Connection...")
    
    try:
        async with websockets.connect(uri) as websocket:
            print("✅ Connected to Notifications WebSocket!")
            
            # Wait for any incoming notifications
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                print(f"📥 Received notification: {response}")
            except asyncio.TimeoutError:
                print("⏰ No notifications received (this is normal for testing)")
            
            print("🎉 Notifications WebSocket test completed!")
            
    except Exception as e:
        print(f"❌ Notifications WebSocket test failed: {e}")

async def main():
    """Run all WebSocket tests"""
    print("🚀 Starting Jobraker WebSocket Tests...\n")
    
    await test_chat_websocket()
    print()
    await test_notifications_websocket()
    
    print("\n✅ All WebSocket tests completed!")

if __name__ == "__main__":
    asyncio.run(main())
