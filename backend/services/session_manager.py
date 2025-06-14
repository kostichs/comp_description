"""
Session Management Service

Handles:
- Session metadata loading and saving
- Session status updates
- File path management
- Session logging setup
"""

import logging
import asyncio
from pathlib import Path
from src.data_io import load_session_metadata, save_session_metadata
from src.pipeline.utils.logging import setup_session_logging

logger = logging.getLogger(__name__)

class SessionManager:
    """Manages session metadata and file operations"""
    
    def __init__(self, session_id: str, project_root: Path):
        self.session_id = session_id
        self.project_root = project_root
        self.session_data = None
        self.all_metadata = []
        
    async def load_session_data(self):
        """Load session metadata and find current session"""
        try:
            self.all_metadata = load_session_metadata()
            self.session_data = next((s for s in self.all_metadata if s.get('session_id') == self.session_id), None)
            
            if not self.session_data:
                raise ValueError(f"Session metadata not found for {self.session_id}")
                
            logger.info(f"Session data loaded for {self.session_id}")
            return self.session_data
            
        except Exception as e:
            logger.error(f"Error loading session metadata: {e}")
            raise
    
    def prepare_file_paths(self):
        """Prepare and validate file paths for session"""
        try:
            input_file_path_rel = self.session_data.get("input_file_path")
            if not input_file_path_rel:
                raise ValueError("input_file_path missing in session metadata.")
                
            input_file_path = self.project_root / input_file_path_rel
            session_dir = self.project_root / "output" / "sessions" / self.session_id
            output_csv_path = session_dir / f"{self.session_id}_results.csv"
            pipeline_log_path = session_dir / "pipeline.log"
            
            # Load context if available
            context_text = None
            context_file_path_rel = self.session_data.get("context_used_path")
            if context_file_path_rel:
                context_file_path = self.project_root / context_file_path_rel
                if context_file_path.exists():
                    try:
                        with open(context_file_path, 'r', encoding='utf-8') as cf:
                            context_text = cf.read().strip() or None
                    except Exception as e_ctx:
                        logger.warning(f"Failed to read context file {context_file_path}: {e_ctx}")
                else:
                    logger.warning(f"Context file path in metadata but file not found: {context_file_path}")
            
            # Update session data with paths
            self.session_data['output_csv_path'] = str(output_csv_path.relative_to(self.project_root))
            self.session_data['pipeline_log_path'] = str(pipeline_log_path.relative_to(self.project_root))
            
            return {
                'input_file_path': input_file_path,
                'output_csv_path': output_csv_path,
                'pipeline_log_path': pipeline_log_path,
                'context_text': context_text
            }
            
        except Exception as e:
            logger.error(f"Error preparing file paths: {e}")
            raise
    
    def setup_logging(self, pipeline_log_path: Path):
        """Setup session-specific logging"""
        try:
            pipeline_log_path.parent.mkdir(parents=True, exist_ok=True)
            setup_session_logging(str(pipeline_log_path))
            
            session_logger = logging.getLogger(f"pipeline.session.{self.session_id}")
            session_logger.info(f"--- Starting Background Processing for Session: {self.session_id} ---")
            
            return session_logger
            
        except Exception as e:
            logger.error(f"Error setting up session logging: {e}")
            raise
    
    def update_status(self, status: str, error_message: str = None, **kwargs):
        """Update session status in metadata"""
        try:
            self.session_data['status'] = status
            self.session_data['error_message'] = error_message
            
            # Update additional fields
            for key, value in kwargs.items():
                self.session_data[key] = value
                
            save_session_metadata(self.all_metadata)
            logger.info(f"Updated session {self.session_id} status to '{status}'")
            
        except Exception as e:
            logger.error(f"Error updating session status: {e}")
            raise
    
    def finalize_session(self, status: str, success_count: int, failure_count: int, error_message: str = None):
        """Final session status update with completion data"""
        try:
            # Reload metadata to get latest changes from other modules
            current_all_metadata = load_session_metadata()
            
            # Find current session in reloaded metadata
            session_idx = -1
            for idx, meta_item in enumerate(current_all_metadata):
                if meta_item.get("session_id") == self.session_id:
                    session_idx = idx
                    break
            
            if session_idx != -1:
                # Update session with final data
                current_all_metadata[session_idx]['status'] = status
                current_all_metadata[session_idx]['processed_count'] = success_count
                current_all_metadata[session_idx]['error_count'] = failure_count
                current_all_metadata[session_idx]['error_message'] = error_message
                current_all_metadata[session_idx]['completion_time'] = asyncio.get_running_loop().time()
                
                save_session_metadata(current_all_metadata)
                
                logger.info(f"Finalized session {self.session_id} - Status: {status}")
                return current_all_metadata[session_idx]
            else:
                logger.error(f"Session {self.session_id} not found in metadata during finalization")
                return None
                
        except Exception as e:
            logger.error(f"Error finalizing session: {e}")
            raise 