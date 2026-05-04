"""
Main entry point - starts NiceGUI web interface and scheduler.
"""
import asyncio
import yaml
from pathlib import Path
from datetime import datetime

from nicegui import ui, app
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from database import Database
from llm_provider import LLMProvider
from agent_core import AgentCore, AgentStatus
from tools.base import get_all_tools, TOOL_REGISTRY


# Load configuration
config_path = Path(__file__).parent / "config.yaml"
with open(config_path) as f:
    config = yaml.safe_load(f)

# Initialize components
db = Database()
llm = LLMProvider(
    model=config["llm"]["model"],
    base_url=config["llm"]["base_url"],
    context_limit=config["llm"]["context_limit"]
)
agent = AgentCore(
    llm=llm,
    db=db,
    security_mode=config["security"]["mode"]
)

# Scheduler for timed tasks
scheduler = AsyncIOScheduler()

# State management
pending_confirmation = None  # Stores pending tool call info
confirmation_event = None  # Event to wait for user confirmation


# UI State
status_labels = {}
log_messages = []
MAX_LOG_MESSAGES = 100


def add_log(level: str, message: str, details: str = None):
    """Add log message and update UI."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_entry = {
        "time": timestamp,
        "level": level,
        "message": message,
        "details": details
    }
    log_messages.insert(0, log_entry)
    
    # Trim old logs
    while len(log_messages) > MAX_LOG_MESSAGES:
        log_messages.pop()
    
    # Update log table if it exists
    try:
        log_table.rows = log_messages[:50]  # Show last 50 in UI
        log_table.update()
    except:
        pass


def update_status(status: AgentStatus):
    """Update status indicator in UI."""
    status_map = {
        AgentStatus.IDLE: ("Idle", "green"),
        AgentStatus.THINKING: ("Thinking...", "orange"),
        AgentStatus.WAITING_CONFIRMATION: ("Waiting Confirmation", "red"),
        AgentStatus.EXECUTING: ("Executing...", "blue"),
        AgentStatus.ERROR: ("Error", "red"),
    }
    
    text, color = status_map.get(status, ("Unknown", "gray"))
    
    if "status_indicator" in globals():
        status_indicator.props(f'color={color}')
        status_label.text = f"Agent Status: {text}"
        status_label.update()


async def request_confirmation(tool_name: str, parameters: dict) -> bool:
    """Show confirmation dialog and wait for user response."""
    global pending_confirmation, confirmation_event
    
    pending_confirmation = {
        "tool": tool_name,
        "params": parameters
    }
    confirmation_event = asyncio.Event()
    
    # Show confirmation dialog
    with ui.dialog() as dialog, ui.card().classes('w-96'):
        ui.label(f"Tool: {tool_name}").classes('text-lg font-bold')
        ui.label("Parameters:").classes('mt-2')
        
        param_text = "\n".join(f"  {k}: {v}" for k, v in parameters.items())
        ui.code(param_text).classes('w-full')
        
        ui.label("Do you want to proceed?").classes('mt-4')
        
        with ui.row():
            approve_btn = ui.button("Approve", on_click=lambda: handle_confirmation(True))
            reject_btn = ui.button("Reject", on_click=lambda: handle_confirmation(False), color='negative')
    
    dialog.open()
    
    # Wait for user response
    await confirmation_event.wait()
    
    # Close dialog
    dialog.close()
    
    # Return result
    return pending_confirmation.get("approved", False)


def handle_confirmation(approved: bool):
    """Handle confirmation dialog response."""
    global pending_confirmation, confirmation_event
    
    if pending_confirmation:
        pending_confirmation["approved"] = approved
    
    if confirmation_event:
        confirmation_event.set()


# Set up agent callbacks
agent.on_status_change = update_status
agent.on_log = add_log
agent.on_confirmation_request = request_confirmation


@ui.page('/')
def main_page():
    """Main dashboard page."""
    
    with ui.header().classes('bg-primary text-white'):
        ui.label('🤖 My-Agent Control Panel').classes('text-xl font-bold')
    
    with ui.column().classes('w-full max-w-6xl mx-auto p-4 gap-4'):
        
        # Status row
        with ui.row().classes('w-full'):
            # Status card
            with ui.card().classes('flex-1'):
                ui.label('Agent Status').classes('text-sm text-gray-500')
                global status_label, status_indicator
                status_label = ui.label('Agent Status: Idle').classes('text-2xl font-bold')
                status_indicator = ui.circular_progress(0.0, show_value=False).props('color=green size=40px')
                
                # Quick actions
                with ui.row().classes('mt-4'):
                    ui.button('Reset Agent', on_click=lambda: reset_agent(), icon='refresh').props('flat')
                    
                    # Security mode toggle
                    current_mode = config["security"]["mode"]
                    mode_toggle = ui.toggle(
                        {'safe': '🔒 Safe', 'trusted': '🔓 Trusted'},
                        value=current_mode,
                        on_change=lambda e: toggle_security_mode(e.value)
                    ).props('outline')
        
        # Log panel
        with ui.card().classes('flex-grow w-full'):
            with ui.row().classes('w-full justify-between items-center'):
                ui.label('Activity Log').classes('text-lg font-bold')
                ui.button('Clear Logs', on_click=lambda: clear_logs(), icon='delete').props('flat size=sm')
            
            # Log table
            columns = [
                {'name': 'time', 'label': 'Time', 'field': 'time', 'sortable': True, 'align': 'left'},
                {'name': 'level', 'label': 'Level', 'field': 'level', 'sortable': True, 'align': 'center'},
                {'name': 'message', 'label': 'Message', 'field': 'message', 'sortable': False, 'align': 'left'},
            ]
            
            global log_table
            log_table = ui.table(
                columns=columns,
                rows=[],
                row_key='time'
            ).classes('w-full').props('flat bordered dense')
            
            # Auto-scroll to top (newest first)
            ui.timer(1.0, lambda: log_table.update())
        
        # Command input
        with ui.card().classes('w-full'):
            ui.label('Send Instruction').classes('text-lg font-bold mb-2')
            
            with ui.row().classes('w-full'):
                command_input = ui.input(
                    placeholder='Enter instruction (e.g., "Open Google and search for Python tutorials")'
                ).classes('flex-grow')
                
                async def send_command():
                    command = command_input.value.strip()
                    if not command:
                        return
                    
                    command_input.value = ''
                    add_log("USER", f"Command: {command}")
                    
                    # Process command
                    try:
                        response = await agent.process_message(command)
                        add_log("AGENT", f"Response: {response[:200]}")
                    except Exception as e:
                        add_log("ERROR", f"Failed to process command: {str(e)}")
                
                ui.button('Send', on_click=send_command, icon='send').props('round')
        
        # Tasks panel
        with ui.card().classes('w-full'):
            with ui.row().classes('w-full justify-between items-center'):
                ui.label('Scheduled Tasks').classes('text-lg font-bold')
                
                def show_new_task_dialog():
                    with ui.dialog() as dialog, ui.card():
                        ui.label('Create New Task').classes('text-lg font-bold')
                        
                        name_input = ui.input('Task Name').classes('w-full')
                        desc_input = ui.input('Description').classes('w-full')
                        cron_input = ui.input('Cron Expression (e.g., "0 8 * * *" for daily 8am)').classes('w-full')
                        workflow_input = ui.textarea('Workflow (JSON format)').classes('w-full')
                        
                        trusted_checkbox = ui.checkbox('Mark as Trusted (skip confirmations)')
                        
                        def create_task():
                            try:
                                import json
                                workflow = json.loads(workflow_input.value)
                                task_id = db.create_task(
                                    name=name_input.value,
                                    description=desc_input.value,
                                    workflow=workflow,
                                    cron=cron_input.value or None,
                                    is_trusted=trusted_checkbox.value
                                )
                                
                                # Schedule if cron provided
                                if cron_input.value:
                                    schedule_task(task_id, cron_input.value, workflow)
                                
                                add_log("INFO", f"Created task: {name_input.value}")
                                dialog.close()
                                refresh_tasks()
                            except Exception as e:
                                ui.notify(f'Error: {str(e)}', color='negative')
                        
                        with ui.row():
                            ui.button('Create', on_click=create_task)
                            ui.button('Cancel', on_click=dialog.close, color='negative')
                    
                    dialog.open()
                
                ui.button('New Task', on_click=show_new_task_dialog, icon='add').props('flat')
            
            # Tasks table
            def load_tasks():
                tasks = db.get_all_tasks()
                task_rows = []
                for task in tasks:
                    task_rows.append({
                        'id': task['id'],
                        'name': task['name'],
                        'cron': task['cron_expression'] or '-',
                        'trusted': '✓' if task['is_trusted'] else '✗',
                        'enabled': '✓' if task['is_enabled'] else '✗',
                    })
                return task_rows
            
            task_columns = [
                {'name': 'id', 'label': 'ID', 'field': 'id', 'sortable': True},
                {'name': 'name', 'label': 'Name', 'field': 'name', 'sortable': True},
                {'name': 'cron', 'label': 'Schedule', 'field': 'cron'},
                {'name': 'trusted', 'label': 'Trusted', 'field': 'trusted'},
                {'name': 'enabled', 'label': 'Enabled', 'field': 'enabled'},
            ]
            
            tasks_table = ui.table(
                columns=task_columns,
                rows=load_tasks(),
                row_key='id'
            ).classes('w-full').props('flat bordered')
            
            def refresh_tasks():
                tasks_table.rows = load_tasks()
                tasks_table.update()
            
            # Add action buttons
            with tasks_table.add_slot('body-cell-action'):
                def render_action_button(cell):
                    with ui.row():
                        if cell.value['enabled']:
                            ui.button(icon='pause', on_click=lambda: toggle_task(cell.value['id'], False)).props('flat size=sm')
                        else:
                            ui.button(icon='play_arrow', on_click=lambda: toggle_task(cell.value['id'], True)).props('flat size=sm')
                        
                        ui.button(icon='delete', on_click=lambda: delete_task(cell.value['id'])).props('flat size=sm color=negative')
                
                tasks_table.add_slot('body-cell-action', render_action_button)


def reset_agent():
    """Reset agent state."""
    agent.reset()
    ui.notify('Agent reset', color='info')


def toggle_security_mode(mode: str):
    """Toggle between safe and trusted modes."""
    agent.set_security_mode(mode)
    config["security"]["mode"] = mode
    ui.notify(f'Security mode: {mode}', color='info')


def clear_logs():
    """Clear all logs."""
    log_messages.clear()
    log_table.rows = []
    log_table.update()
    ui.notify('Logs cleared', color='info')


def schedule_task(task_id: int, cron_expr: str, workflow: list):
    """Schedule a task with cron expression."""
    
    async def run_scheduled_task():
        try:
            add_log("SCHEDULER", f"Running scheduled task {task_id}")
            await agent.run_workflow(workflow, task_id=task_id)
        except Exception as e:
            add_log("ERROR", f"Scheduled task {task_id} failed: {str(e)}")
    
    # Parse cron expression
    try:
        trigger = CronTrigger.from_crontab(cron_expr)
        scheduler.add_job(run_scheduled_task, trigger=trigger, id=f'task_{task_id}')
    except Exception as e:
        add_log("ERROR", f"Failed to schedule task {task_id}: {str(e)}")


def toggle_task(task_id: int, enable: bool):
    """Enable or disable a task."""
    db.update_task(id=task_id, is_enabled=enable)
    
    job_id = f'task_{task_id}'
    if enable:
        # Re-schedule
        task = db.get_task(task_id)
        if task and task['cron_expression']:
            import json
            workflow = json.loads(task['workflow_json'])
            schedule_task(task_id, task['cron_expression'], workflow)
    else:
        # Remove from scheduler
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
    
    ui.notify(f'Task {"enabled" if enable else "disabled"}', color='info')


def delete_task(task_id: int):
    """Delete a task."""
    # Remove from scheduler
    job_id = f'task_{task_id}'
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
    
    db.delete_task(task_id)
    ui.notify('Task deleted', color='info')


def load_scheduled_tasks():
    """Load and schedule all enabled tasks from database."""
    tasks = db.get_all_tasks()
    for task in tasks:
        if task['is_enabled'] and task['cron_expression']:
            import json
            workflow = json.loads(task['workflow_json'])
            schedule_task(task['id'], task['cron_expression'], workflow)


# Initialize on startup
@app.get('/ready')
def ready():
    """Health check endpoint."""
    return {'status': 'ready'}


if __name__ in {"__main__", "__mp_main__"}:
    # Load scheduled tasks
    if config["scheduler"]["enabled"]:
        scheduler.start()
        load_scheduled_tasks()
        print(f"Scheduler started with {len(scheduler.get_jobs())} jobs")
    
    # Start NiceGUI
    ui.run(
        title='My-Agent Control Panel',
        host='localhost',
        port=8080,
        reload=False
    )
