"""
Task Service for GeoSense Platform API

Provides background task execution and management using Celery:
- Async task submission for long-running operations
- Task status monitoring and progress tracking
- Result retrieval and error handling
- Integration with all domain services for async execution
- Celery task queue management

This service enables non-blocking execution of compute-intensive workflows.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from typing import Dict, List, Optional, Any, Callable
from datetime import datetime
import logging

# Import Celery infrastructure
try:
    from ops.worker import celery_app
    from celery.result import AsyncResult
    CELERY_AVAILABLE = True
except ImportError as e:
    CELERY_AVAILABLE = False
    print(f"Celery imports not available: {e}")

# Import services for async execution
try:
    from api.services import (
        get_simulation_service,
        get_inversion_service,
        get_control_service,
        get_ml_service,
        get_trade_study_service,
        get_database_service
    )
    SERVICES_AVAILABLE = True
except ImportError as e:
    SERVICES_AVAILABLE = False
    print(f"Service imports not available: {e}")

logger = logging.getLogger(__name__)


class TaskService:
    """
    Service for background task execution and management.

    Provides high-level task submission, monitoring, and result retrieval
    for long-running operations that should run asynchronously.
    """

    def __init__(self):
        """Initialize task service."""
        if not CELERY_AVAILABLE:
            print("Warning: Celery not available.")
            return

        self.celery_app = celery_app

    # =================================================================
    # Task Registration
    # =================================================================

    def register_service_tasks(self):
        """
        Register service methods as Celery tasks dynamically.

        This allows any service method to be executed asynchronously.
        """
        if not CELERY_AVAILABLE or not SERVICES_AVAILABLE:
            return

        # Define task wrappers for each service
        task_definitions = {
            # Simulation tasks
            'simulation.propagate_formation': self._wrap_task(
                get_simulation_service, 'propagate_formation'
            ),
            'simulation.generate_measurements': self._wrap_task(
                get_simulation_service, 'generate_measurements'
            ),

            # Inversion tasks
            'inversion.estimate_gravity': self._wrap_task(
                get_inversion_service, 'estimate_gravity'
            ),
            'inversion.validate_results': self._wrap_task(
                get_inversion_service, 'validate_results'
            ),

            # Control tasks
            'control.compute_station_keeping': self._wrap_task(
                get_control_service, 'compute_station_keeping'
            ),

            # ML tasks
            'ml.train_pinn': self._wrap_task(
                get_ml_service, 'train_pinn'
            ),
            'ml.train_unet': self._wrap_task(
                get_ml_service, 'train_unet'
            ),
            'ml.unet_inference': self._wrap_task(
                get_ml_service, 'unet_inference'
            ),

            # Trade study tasks
            'trade_study.run_baseline_study': self._wrap_task(
                get_trade_study_service, 'run_baseline_study'
            ),
            'trade_study.run_orbit_study': self._wrap_task(
                get_trade_study_service, 'run_orbit_study'
            ),
        }

        # Register tasks with Celery
        for task_name, task_func in task_definitions.items():
            self.celery_app.task(name=task_name, bind=True)(task_func)

    def _wrap_task(self, service_getter: Callable, method_name: str):
        """Wrap a service method for async execution."""
        def task_wrapper(self_celery, *args, **kwargs):
            try:
                # Get service instance
                service = service_getter()
                method = getattr(service, method_name)

                # Execute method
                result = method(**kwargs)

                return {
                    'status': 'success',
                    'result': result,
                    'task_name': self_celery.request.task,
                    'task_id': self_celery.request.id
                }
            except Exception as e:
                logger.error(f"Task {self_celery.request.task} failed: {e}")
                return {
                    'status': 'error',
                    'error': str(e),
                    'task_name': self_celery.request.task,
                    'task_id': self_celery.request.id
                }

        return task_wrapper

    # =================================================================
    # Task Submission
    # =================================================================

    def submit_task(
        self,
        task_name: str,
        parameters: Dict[str, Any],
        priority: int = 5,
        countdown: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Submit task for async execution.

        Args:
            task_name: Fully qualified task name (e.g., 'simulation.propagate_formation')
            parameters: Task parameters
            priority: Task priority (0-10, higher = more priority)
            countdown: Delay before execution (seconds)

        Returns:
            Task submission details with task_id
        """
        if not CELERY_AVAILABLE:
            raise RuntimeError("Celery not available")

        try:
            # Submit task to Celery
            task = self.celery_app.send_task(
                task_name,
                kwargs=parameters,
                priority=priority,
                countdown=countdown
            )

            return {
                'task_id': task.id,
                'task_name': task_name,
                'status': 'submitted',
                'submitted_at': datetime.utcnow().isoformat(),
                'priority': priority,
                'countdown': countdown
            }
        except Exception as e:
            raise RuntimeError(f"Failed to submit task: {e}")

    def submit_chain(
        self,
        tasks: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Submit chain of tasks to execute sequentially.

        Args:
            tasks: List of task definitions, each with 'task_name' and 'parameters'

        Returns:
            Chain submission details
        """
        if not CELERY_AVAILABLE:
            raise RuntimeError("Celery not available")

        try:
            from celery import chain

            # Build task chain
            task_signatures = []
            for task_def in tasks:
                sig = self.celery_app.signature(
                    task_def['task_name'],
                    kwargs=task_def.get('parameters', {})
                )
                task_signatures.append(sig)

            # Execute chain
            result = chain(*task_signatures).apply_async()

            return {
                'chain_id': result.id,
                'task_count': len(tasks),
                'tasks': [t['task_name'] for t in tasks],
                'status': 'submitted',
                'submitted_at': datetime.utcnow().isoformat()
            }
        except Exception as e:
            raise RuntimeError(f"Failed to submit task chain: {e}")

    def submit_group(
        self,
        tasks: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Submit group of tasks to execute in parallel.

        Args:
            tasks: List of task definitions

        Returns:
            Group submission details
        """
        if not CELERY_AVAILABLE:
            raise RuntimeError("Celery not available")

        try:
            from celery import group

            # Build task group
            task_signatures = []
            for task_def in tasks:
                sig = self.celery_app.signature(
                    task_def['task_name'],
                    kwargs=task_def.get('parameters', {})
                )
                task_signatures.append(sig)

            # Execute group
            result = group(*task_signatures).apply_async()

            return {
                'group_id': result.id,
                'task_count': len(tasks),
                'tasks': [t['task_name'] for t in tasks],
                'status': 'submitted',
                'submitted_at': datetime.utcnow().isoformat()
            }
        except Exception as e:
            raise RuntimeError(f"Failed to submit task group: {e}")

    # =================================================================
    # Task Monitoring
    # =================================================================

    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """
        Get task execution status.

        Args:
            task_id: Celery task ID

        Returns:
            Task status and metadata
        """
        if not CELERY_AVAILABLE:
            raise RuntimeError("Celery not available")

        try:
            result = AsyncResult(task_id, app=self.celery_app)

            status_info = {
                'task_id': task_id,
                'status': result.state,
                'ready': result.ready(),
                'successful': result.successful() if result.ready() else None,
                'failed': result.failed() if result.ready() else None,
            }

            # Add result if available
            if result.ready():
                if result.successful():
                    status_info['result'] = result.result
                elif result.failed():
                    status_info['error'] = str(result.info)

            # Add progress info if available
            if hasattr(result, 'info') and isinstance(result.info, dict):
                status_info['progress'] = result.info.get('progress')
                status_info['current'] = result.info.get('current')
                status_info['total'] = result.info.get('total')

            return status_info
        except Exception as e:
            raise RuntimeError(f"Failed to get task status: {e}")

    def get_task_result(self, task_id: str, timeout: Optional[float] = None) -> Dict[str, Any]:
        """
        Get task result (blocks until complete).

        Args:
            task_id: Celery task ID
            timeout: Maximum time to wait (seconds)

        Returns:
            Task result
        """
        if not CELERY_AVAILABLE:
            raise RuntimeError("Celery not available")

        try:
            result = AsyncResult(task_id, app=self.celery_app)

            # Wait for result
            task_result = result.get(timeout=timeout)

            return {
                'task_id': task_id,
                'status': 'completed',
                'result': task_result
            }
        except Exception as e:
            raise RuntimeError(f"Failed to get task result: {e}")

    def list_active_tasks(self) -> Dict[str, Any]:
        """
        List all active tasks.

        Returns:
            Active task information
        """
        if not CELERY_AVAILABLE:
            raise RuntimeError("Celery not available")

        try:
            # Get active tasks from workers
            inspect = self.celery_app.control.inspect()
            active = inspect.active()

            if not active:
                return {
                    'active_tasks': [],
                    'count': 0
                }

            # Flatten task list
            all_tasks = []
            for worker_name, tasks in active.items():
                for task in tasks:
                    all_tasks.append({
                        'task_id': task['id'],
                        'task_name': task['name'],
                        'worker': worker_name,
                        'args': task.get('args', []),
                        'kwargs': task.get('kwargs', {}),
                        'time_start': task.get('time_start')
                    })

            return {
                'active_tasks': all_tasks,
                'count': len(all_tasks),
                'workers': list(active.keys())
            }
        except Exception as e:
            raise RuntimeError(f"Failed to list active tasks: {e}")

    def list_scheduled_tasks(self) -> Dict[str, Any]:
        """
        List scheduled (pending) tasks.

        Returns:
            Scheduled task information
        """
        if not CELERY_AVAILABLE:
            raise RuntimeError("Celery not available")

        try:
            inspect = self.celery_app.control.inspect()
            scheduled = inspect.scheduled()

            if not scheduled:
                return {
                    'scheduled_tasks': [],
                    'count': 0
                }

            # Flatten task list
            all_tasks = []
            for worker_name, tasks in scheduled.items():
                for task in tasks:
                    all_tasks.append({
                        'task_id': task['request']['id'],
                        'task_name': task['request']['name'],
                        'worker': worker_name,
                        'eta': task.get('eta')
                    })

            return {
                'scheduled_tasks': all_tasks,
                'count': len(all_tasks)
            }
        except Exception as e:
            raise RuntimeError(f"Failed to list scheduled tasks: {e}")

    # =================================================================
    # Task Control
    # =================================================================

    def cancel_task(self, task_id: str, terminate: bool = False) -> Dict[str, Any]:
        """
        Cancel running task.

        Args:
            task_id: Celery task ID
            terminate: Force terminate (vs graceful revoke)

        Returns:
            Cancellation confirmation
        """
        if not CELERY_AVAILABLE:
            raise RuntimeError("Celery not available")

        try:
            result = AsyncResult(task_id, app=self.celery_app)
            result.revoke(terminate=terminate)

            return {
                'task_id': task_id,
                'cancelled': True,
                'terminated': terminate,
                'cancelled_at': datetime.utcnow().isoformat()
            }
        except Exception as e:
            raise RuntimeError(f"Failed to cancel task: {e}")

    def retry_task(self, task_id: str) -> Dict[str, Any]:
        """
        Retry failed task.

        Args:
            task_id: Celery task ID

        Returns:
            Retry submission details
        """
        if not CELERY_AVAILABLE:
            raise RuntimeError("Celery not available")

        try:
            # Get original task
            result = AsyncResult(task_id, app=self.celery_app)

            if not result.failed():
                raise ValueError("Task has not failed, cannot retry")

            # Resubmit with same parameters
            # Note: This is simplified - in production would need to store original parameters
            new_task = result.retry()

            return {
                'original_task_id': task_id,
                'new_task_id': new_task.id,
                'status': 'retrying',
                'retried_at': datetime.utcnow().isoformat()
            }
        except Exception as e:
            raise RuntimeError(f"Failed to retry task: {e}")

    # =================================================================
    # Worker Management
    # =================================================================

    def get_worker_stats(self) -> Dict[str, Any]:
        """
        Get Celery worker statistics.

        Returns:
            Worker stats and health info
        """
        if not CELERY_AVAILABLE:
            raise RuntimeError("Celery not available")

        try:
            inspect = self.celery_app.control.inspect()

            stats = inspect.stats()
            active = inspect.active()
            registered = inspect.registered()

            if not stats:
                return {
                    'workers': [],
                    'count': 0,
                    'status': 'no_workers'
                }

            workers = []
            for worker_name, worker_stats in stats.items():
                workers.append({
                    'name': worker_name,
                    'pool': worker_stats.get('pool', {}).get('implementation'),
                    'max_concurrency': worker_stats.get('pool', {}).get('max-concurrency'),
                    'active_tasks': len(active.get(worker_name, [])) if active else 0,
                    'registered_tasks': len(registered.get(worker_name, [])) if registered else 0,
                    'uptime': worker_stats.get('uptime')
                })

            return {
                'workers': workers,
                'count': len(workers),
                'status': 'healthy' if workers else 'no_workers'
            }
        except Exception as e:
            raise RuntimeError(f"Failed to get worker stats: {e}")

    def ping_workers(self) -> Dict[str, Any]:
        """
        Ping all workers to check connectivity.

        Returns:
            Worker ping responses
        """
        if not CELERY_AVAILABLE:
            raise RuntimeError("Celery not available")

        try:
            responses = self.celery_app.control.ping(timeout=1.0)

            return {
                'workers': responses,
                'count': len(responses) if responses else 0,
                'all_responsive': len(responses) > 0 if responses else False
            }
        except Exception as e:
            raise RuntimeError(f"Failed to ping workers: {e}")


# Singleton
_task_service = None

def get_task_service() -> TaskService:
    """Get or create task service singleton."""
    global _task_service
    if _task_service is None:
        _task_service = TaskService()
    return _task_service
