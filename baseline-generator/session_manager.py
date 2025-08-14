#!/usr/bin/env python3
"""
Session management for baseline runner.
Allows saving and resuming progress for long-running processes.
"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List
import logging

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages session state for baseline runner"""
    
    def __init__(self, session_dir: Path):
        """Initialize session manager with a directory for session files"""
        self.session_dir = Path(session_dir)
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.session_file = self.session_dir / 'session_state.json'
        self.state = self._load_state()
    
    def _load_state(self) -> Dict[str, Any]:
        """Load existing session state or create new one"""
        if self.session_file.exists():
            try:
                with open(self.session_file, 'r') as f:
                    state = json.load(f)
                logger.info(f"Loaded existing session from {self.session_file}")
                return state
            except Exception as e:
                logger.warning(f"Failed to load session state: {e}")
                return self._create_new_state()
        else:
            return self._create_new_state()
    
    def _create_new_state(self) -> Dict[str, Any]:
        """Create a new session state"""
        return {
            'session_id': datetime.now().isoformat(),
            'created_at': datetime.now().isoformat(),
            'last_updated': datetime.now().isoformat(),
            'dataset_path': None,
            'output_dir': None,
            'model': None,
            'completed_projects': [],
            'failed_projects': [],
            'current_project': None,
            'current_project_progress': {
                'codebases_completed': [],
                'files_analyzed': [],
                'last_file': None
            },
            'total_projects': 0,
            'projects_completed': 0,
            'projects_failed': 0,
            'total_findings': 0,
            'is_complete': False
        }
    
    def save_state(self):
        """Save current state to disk"""
        self.state['last_updated'] = datetime.now().isoformat()
        with open(self.session_file, 'w') as f:
            json.dump(self.state, f, indent=2)
        logger.debug(f"Session state saved to {self.session_file}")
    
    def start_session(self, dataset_path: str, output_dir: str, model: str, total_projects: int):
        """Start a new session or resume existing one"""
        if self.state['dataset_path'] != dataset_path:
            # Different dataset, reset state
            logger.info("Starting new session for different dataset")
            self.state = self._create_new_state()
        
        self.state['dataset_path'] = dataset_path
        self.state['output_dir'] = output_dir
        self.state['model'] = model
        self.state['total_projects'] = total_projects
        self.save_state()
    
    def should_skip_project(self, project_id: str) -> bool:
        """Check if a project should be skipped (already completed or failed)"""
        return (project_id in self.state['completed_projects'] or 
                project_id in self.state['failed_projects'])
    
    def start_project(self, project_id: str, project_name: str):
        """Mark a project as started"""
        logger.info(f"Starting project: {project_name} ({project_id})")
        self.state['current_project'] = {
            'project_id': project_id,
            'project_name': project_name,
            'started_at': datetime.now().isoformat()
        }
        self.state['current_project_progress'] = {
            'codebases_completed': [],
            'files_analyzed': [],
            'last_file': None
        }
        self.save_state()
    
    def update_project_progress(self, codebase_url: str = None, file_path: str = None):
        """Update progress within current project"""
        if codebase_url and codebase_url not in self.state['current_project_progress']['codebases_completed']:
            self.state['current_project_progress']['codebases_completed'].append(codebase_url)
        
        if file_path:
            self.state['current_project_progress']['files_analyzed'].append(file_path)
            self.state['current_project_progress']['last_file'] = file_path
        
        self.save_state()
    
    def complete_project(self, project_id: str, findings_count: int = 0):
        """Mark a project as completed"""
        logger.info(f"Completed project: {project_id} with {findings_count} findings")
        
        if project_id not in self.state['completed_projects']:
            self.state['completed_projects'].append(project_id)
            self.state['projects_completed'] += 1
            self.state['total_findings'] += findings_count
        
        # Clear current project
        self.state['current_project'] = None
        self.state['current_project_progress'] = {
            'codebases_completed': [],
            'files_analyzed': [],
            'last_file': None
        }
        
        # Check if all projects are done
        if self.state['projects_completed'] + self.state['projects_failed'] >= self.state['total_projects']:
            self.state['is_complete'] = True
        
        self.save_state()
    
    def fail_project(self, project_id: str, error: str):
        """Mark a project as failed"""
        logger.error(f"Failed project: {project_id} - {error}")
        
        if project_id not in self.state['failed_projects']:
            self.state['failed_projects'].append(project_id)
            self.state['projects_failed'] += 1
        
        # Clear current project
        self.state['current_project'] = None
        self.state['current_project_progress'] = {
            'codebases_completed': [],
            'files_analyzed': [],
            'last_file': None
        }
        
        # Check if all projects are done
        if self.state['projects_completed'] + self.state['projects_failed'] >= self.state['total_projects']:
            self.state['is_complete'] = True
        
        self.save_state()
    
    def get_resume_info(self) -> Dict[str, Any]:
        """Get information about what can be resumed"""
        return {
            'has_session': self.session_file.exists(),
            'session_id': self.state.get('session_id'),
            'created_at': self.state.get('created_at'),
            'last_updated': self.state.get('last_updated'),
            'dataset_path': self.state.get('dataset_path'),
            'projects_completed': self.state.get('projects_completed', 0),
            'projects_failed': self.state.get('projects_failed', 0),
            'total_projects': self.state.get('total_projects', 0),
            'current_project': self.state.get('current_project'),
            'is_complete': self.state.get('is_complete', False)
        }
    
    def clear_session(self):
        """Clear the current session"""
        if self.session_file.exists():
            os.unlink(self.session_file)
            logger.info("Session cleared")
        self.state = self._create_new_state()
    
    def get_progress_percentage(self) -> float:
        """Get the completion percentage"""
        if self.state['total_projects'] == 0:
            return 0.0
        completed = self.state['projects_completed'] + self.state['projects_failed']
        return (completed / self.state['total_projects']) * 100
    
    def print_resume_summary(self):
        """Print a summary of the resume state"""
        info = self.get_resume_info()
        
        if not info['has_session']:
            print("No existing session found. Starting fresh.")
            return
        
        print("\n" + "="*60)
        print("RESUMING PREVIOUS SESSION")
        print("="*60)
        print(f"Session ID: {info['session_id']}")
        print(f"Started: {info['created_at']}")
        print(f"Last updated: {info['last_updated']}")
        print(f"Dataset: {info['dataset_path']}")
        print(f"\nProgress: {info['projects_completed'] + info['projects_failed']}/{info['total_projects']} projects")
        print(f"  - Completed: {info['projects_completed']}")
        print(f"  - Failed: {info['projects_failed']}")
        print(f"  - Remaining: {info['total_projects'] - info['projects_completed'] - info['projects_failed']}")
        
        if info['current_project']:
            print(f"\nResuming from project: {info['current_project']['project_name']}")
        
        print(f"\nProgress: {self.get_progress_percentage():.1f}%")
        print("="*60 + "\n")