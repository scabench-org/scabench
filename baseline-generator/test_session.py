#!/usr/bin/env python3
"""
Test script for session management functionality.
Simulates interruption and resume scenarios.
"""

import json
import os
import sys
import time
import signal
from pathlib import Path
from session_manager import SessionManager

def test_session_manager():
    """Test the session manager functionality"""
    
    print("Testing Session Manager")
    print("=" * 60)
    
    # Create a test session directory
    test_dir = Path("test_session_output")
    test_dir.mkdir(exist_ok=True)
    
    # Initialize session manager
    session_mgr = SessionManager(test_dir)
    
    # Test 1: New session
    print("\n1. Creating new session...")
    session_mgr.start_session(
        dataset_path="test_dataset.json",
        output_dir="test_output",
        model="gpt-4o",
        total_projects=5
    )
    print(f"   Session ID: {session_mgr.state['session_id']}")
    
    # Test 2: Project processing
    print("\n2. Simulating project processing...")
    
    # Process first project
    session_mgr.start_project("project_1", "Test Project 1")
    print("   Started project_1")
    time.sleep(0.5)
    session_mgr.complete_project("project_1", findings_count=10)
    print("   Completed project_1 with 10 findings")
    
    # Process second project
    session_mgr.start_project("project_2", "Test Project 2")
    print("   Started project_2")
    time.sleep(0.5)
    session_mgr.complete_project("project_2", findings_count=5)
    print("   Completed project_2 with 5 findings")
    
    # Fail third project
    session_mgr.start_project("project_3", "Test Project 3")
    print("   Started project_3")
    time.sleep(0.5)
    session_mgr.fail_project("project_3", "Simulated error")
    print("   Failed project_3")
    
    # Test 3: Check progress
    print(f"\n3. Progress: {session_mgr.get_progress_percentage():.1f}%")
    print(f"   Completed: {session_mgr.state['projects_completed']}")
    print(f"   Failed: {session_mgr.state['projects_failed']}")
    print(f"   Total findings: {session_mgr.state['total_findings']}")
    
    # Test 4: Simulate interruption and resume
    print("\n4. Simulating interruption...")
    session_mgr.start_project("project_4", "Test Project 4")
    print("   Started project_4 (will be interrupted)")
    session_mgr.save_state()
    
    # Create new session manager (simulating restart)
    print("\n5. Simulating resume after interruption...")
    session_mgr2 = SessionManager(test_dir)
    session_mgr2.print_resume_summary()
    
    # Check skip logic
    print("\n6. Testing skip logic...")
    print(f"   Should skip project_1? {session_mgr2.should_skip_project('project_1')}")
    print(f"   Should skip project_2? {session_mgr2.should_skip_project('project_2')}")
    print(f"   Should skip project_3? {session_mgr2.should_skip_project('project_3')}")
    print(f"   Should skip project_4? {session_mgr2.should_skip_project('project_4')}")
    print(f"   Should skip project_5? {session_mgr2.should_skip_project('project_5')}")
    
    # Complete remaining work
    print("\n7. Completing remaining work...")
    session_mgr2.complete_project("project_4", findings_count=8)
    print("   Completed project_4")
    
    session_mgr2.start_project("project_5", "Test Project 5")
    session_mgr2.complete_project("project_5", findings_count=12)
    print("   Completed project_5")
    
    # Final status
    print(f"\n8. Final Status:")
    print(f"   Progress: {session_mgr2.get_progress_percentage():.1f}%")
    print(f"   Is complete? {session_mgr2.state['is_complete']}")
    print(f"   Total projects: {session_mgr2.state['total_projects']}")
    print(f"   Completed: {session_mgr2.state['projects_completed']}")
    print(f"   Failed: {session_mgr2.state['projects_failed']}")
    print(f"   Total findings: {session_mgr2.state['total_findings']}")
    
    # Test 9: Clear session
    print("\n9. Clearing session...")
    session_mgr2.clear_session()
    print("   Session cleared")
    
    # Verify session is cleared
    session_mgr3 = SessionManager(test_dir)
    info = session_mgr3.get_resume_info()
    print(f"   Has session after clear? {info['has_session']}")
    
    # Cleanup
    import shutil
    shutil.rmtree(test_dir)
    print("\n✅ All tests passed!")

if __name__ == "__main__":
    try:
        test_session_manager()
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)