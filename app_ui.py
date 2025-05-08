import tkinter as tk
from tkinter import ttk
from tkinter import filedialog, messagebox
import os
import subprocess # For opening folder cross-platform
import threading
import queue
import asyncio
import time
import logging # Added for logging
# We will need to import pipeline functions later
from src.pipeline import run_pipeline_for_file, load_env_vars, load_llm_config
from src.data_io import save_results_csv, load_session_metadata, save_session_metadata, ensure_sessions_dir_exists, SESSIONS_DIR # Added session imports, SESSIONS_DIR
from openai import AsyncOpenAI
from scrapingbee import ScrapingBeeClient
import aiohttp
import sys # Added for platform check
import traceback # Added for thread error reporting
import pandas as pd # Added for reading CSV results

class CompanyApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Company Information Processor")
        self.root.geometry("800x600")

        # Variables
        self.input_file_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Ready")
        self.current_input_file = None
        self.current_session_id = None # Track current session
        self.session_metadata = load_session_metadata() # Load metadata on init
        self.session_ids = [s['session_id'] for s in self.session_metadata]
        self.selected_session_var = tk.StringVar()
        
        self.process_thread = None
        self.queue = queue.Queue()

        # Configure main window grid
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(3, weight=1) # Row for table frame

        # --- Session Selection Frame (NEW) ---
        session_frame = ttk.LabelFrame(self.root, text="Session Management", padding="5")
        session_frame.grid(row=0, column=0, padx=10, pady=5, sticky="ew")
        session_frame.grid_columnconfigure(1, weight=1)

        self.new_session_button = ttk.Button(session_frame, text="New Session", command=self.create_new_session)
        self.new_session_button.grid(row=0, column=0, padx=5, pady=5, sticky="w")

        ttk.Label(session_frame, text="Load Session:").grid(row=0, column=1, padx=(20, 5), pady=5, sticky="e")
        self.session_combobox = ttk.Combobox(session_frame, textvariable=self.selected_session_var, values=self.session_ids, state="readonly")
        self.session_combobox.grid(row=0, column=2, padx=5, pady=5, sticky="ew")
        self.session_combobox.bind("<<ComboboxSelected>>", self.load_selected_session)
        if self.session_ids: self.session_combobox.current(len(self.session_ids)-1) # Select last session by default?

        # --- Input File Frame (Modified) ---
        input_frame = ttk.LabelFrame(self.root, text="Input Configuration (for New or Current Session)", padding="5")
        input_frame.grid(row=1, column=0, padx=10, pady=5, sticky="ew")
        input_frame.grid_columnconfigure(1, weight=1)
        ttk.Label(input_frame, text="Input File:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.input_entry = ttk.Entry(input_frame, textvariable=self.input_file_var, state='readonly', width=80)
        self.input_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        self.browse_button = ttk.Button(input_frame, text="Browse...", command=self.browse_input_file)
        self.browse_button.grid(row=0, column=2, padx=5, pady=5)
        
        # --- Context Frame (Modified) ---
        context_frame = ttk.LabelFrame(self.root, text="Context (for New or Current Session)", padding="5")
        context_frame.grid(row=2, column=0, padx=10, pady=5, sticky="ew")
        context_frame.grid_columnconfigure(0, weight=1)
        self.context_area = tk.Text(context_frame, height=3, width=80)
        self.context_area.grid(row=0, column=0, padx=5, pady=5, sticky="ew")

        # --- Table Frame ---
        table_frame = ttk.LabelFrame(self.root, text="Results", padding="5")
        table_frame.grid(row=3, column=0, padx=10, pady=5, sticky="nsew") # Adjusted row
        table_frame.grid_columnconfigure(0, weight=1)
        table_frame.grid_rowconfigure(0, weight=1)
        
        self.columns = ("name", "homepage", "linkedin", "description")
        self.tree = ttk.Treeview(table_frame, columns=self.columns, show='headings')
        self.tree.heading("name", text="Company Name")
        self.tree.heading("homepage", text="Homepage")
        self.tree.heading("linkedin", text="LinkedIn")
        self.tree.heading("description", text="Description")
        self.tree.column("name", width=200, anchor=tk.W)
        self.tree.column("homepage", width=200, anchor=tk.W)
        self.tree.column("linkedin", width=200, anchor=tk.W)
        self.tree.column("description", width=400, anchor=tk.W)
        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        hsb.grid(row=1, column=0, sticky='ew')

        # --- Controls Frame (Modified) ---
        controls_frame = ttk.Frame(self.root, padding="5")
        controls_frame.grid(row=4, column=0, padx=10, pady=5, sticky="ew") # Adjusted row
        controls_frame.grid_columnconfigure(0, weight=1) 
        controls_frame.grid_columnconfigure(1, weight=1) 
        controls_frame.grid_columnconfigure(2, weight=1)

        # Removed browse button from here, moved New Session up
        self.start_button = ttk.Button(controls_frame, text="Start Processing", command=self.start_processing)
        self.start_button.grid(row=0, column=1, padx=5, pady=5) # Keep centered

        self.open_folder_button = ttk.Button(controls_frame, text="Open Session Folder", command=self.open_output_folder) # Text changed
        self.open_folder_button.grid(row=0, column=2, padx=5, pady=5, sticky="e")

        # --- Status Bar ---
        status_frame = ttk.Frame(self.root, relief=tk.SUNKEN, padding="2")
        status_frame.grid(row=5, column=0, sticky="ew") # Adjusted row
        self.status_label = ttk.Label(status_frame, textvariable=self.status_var, anchor="w")
        self.status_label.pack(fill=tk.X, padx=5)
        
        # Load last session on startup if exists
        if self.session_ids:
            self.session_combobox.current(len(self.session_ids)-1) # Select last item
            self.load_selected_session(None) # Load the data for the last session
        else:
            self.create_new_session() # Start with a new session state if none exist
            
        # Start checking the queue
        self.check_queue()

    def create_new_session(self):
        """Resets the UI state for a new session."""
        self.current_session_id = None # Indicate new session state
        self.current_input_file = None
        self.input_file_var.set("")
        self.context_area.delete("1.0", tk.END)
        self.clear_treeview()
        self.selected_session_var.set("") # Clear combobox selection
        self.status_var.set("Ready for new session. Select input file.")
        self.enable_controls()
        # print("UI reset for new session.") # Debug print
        
    def load_selected_session(self, event):
        """Loads the data associated with the selected session."""
        selected_id = self.selected_session_var.get()
        if not selected_id:
            return
        
        # print(f"Loading session: {selected_id}") # Debug print
        self.current_session_id = selected_id
        # Reload metadata in case it changed in background
        self.session_metadata = load_session_metadata()
        session_data = next((s for s in self.session_metadata if s['session_id'] == selected_id), None)
        
        if session_data:
            self.current_input_file = session_data.get("original_input_file")
            self.input_file_var.set(self.current_input_file or "")
            
            self.context_area.delete("1.0", tk.END)
            context_to_insert = session_data.get("context_used", "")
            if context_to_insert:
                self.context_area.insert("1.0", context_to_insert)
            
            self.clear_treeview()
            output_csv_path = session_data.get("output_csv")
            session_status = session_data.get('status', 'unknown')

            # <<< START: Reset 'running' status on load if no active thread >>>
            if session_status == 'running':
                # As the app just started, no thread can actually be running for this session yet.
                # So, if we find a session marked 'running', it means it was interrupted.
                session_data['status'] = 'interrupted' # Change status
                session_status = 'interrupted' # Update local variable for current logic
                save_session_metadata(self.session_metadata) # Save updated metadata
                logging.info(f"Session '{selected_id}' was found as 'running', reset to 'interrupted'.")
            # <<< END: Reset 'running' status >>>
            
            if output_csv_path and os.path.exists(output_csv_path):
                if session_status == 'completed' or session_status == 'error': # Load results if completed or errored
                     self.load_results_to_table(output_csv_path)
                     self.status_var.set(f"Loaded session: {selected_id}. Status: {session_status}")
                elif session_status == 'running':
                     self.status_var.set(f"Session {selected_id} is currently running. Results will load upon completion.")
                     self.disable_controls()
                else: # starting or unknown
                     self.status_var.set(f"Loaded session: {selected_id}. Status: {session_status}. No results loaded yet.")
            else:
                self.status_var.set(f"Loaded session: {selected_id}. Status: {session_status}. No results file found.")
                
            # Enable/disable controls based on status (disable if running)
            if session_status != 'running':
                 self.enable_controls() 
            else:
                 self.disable_controls()
        else:
            messagebox.showerror("Error", f"Could not find metadata for session ID: {selected_id}")
            self.status_var.set(f"Error loading session {selected_id}.")
            self.create_new_session() # Reset to new session state on error
            
    def load_results_to_table(self, csv_path):
        """Loads data from a CSV file into the Treeview."""
        try:
            # Check if file has content beyond just header
            if os.path.getsize(csv_path) < 50: # Arbitrary small size check for header
                logging.warning(f"Results file seems empty (or header only): {csv_path}")
                self.clear_treeview()
                return
                
            df = pd.read_csv(csv_path, sep=',', encoding='utf-8-sig')
            # Ensure required columns exist, fill missing with empty string
            for col in self.columns:
                if col not in df.columns:
                    df[col] = ""
            # Reorder df columns to match self.columns for insertion
            df = df[list(self.columns)]
                
            self.clear_treeview()
            for index, row in df.iterrows():
                # Convert row values to strings for Treeview
                values = [str(row[col]) if pd.notna(row[col]) else "" for col in self.columns]
                self.tree.insert("", tk.END, values=values)
            logging.info(f"Loaded {len(df)} rows from {os.path.basename(csv_path)} into table.")
        except FileNotFoundError:
            logging.warning(f"Results file not found when trying to load: {csv_path}")
            self.clear_treeview()
        except pd.errors.EmptyDataError:
             logging.warning(f"Results file is empty: {csv_path}")
             self.clear_treeview()
        except Exception as e:
            logging.error(f"Error reading or displaying results from {csv_path}: {e}")
            messagebox.showerror("Error", f"Failed to load results from:\n{csv_path}\nError: {e}")
            self.clear_treeview()

    def browse_input_file(self):
        """Opens a file dialog to select the input CSV or Excel file."""
        filetypes = (
            ('Excel files', '*.xlsx *.xls'),
            ('CSV files', '*.csv'),
            ('All files', '*.*')
        )
        filepath = filedialog.askopenfilename(
            title='Select Input File',
            filetypes=filetypes
        )
        if filepath: # If a file was selected (not cancelled)
            self.create_new_session() 
            self.current_input_file = filepath
            self.input_file_var.set(filepath)
            self.status_var.set(f"Selected input for new session: {os.path.basename(filepath)}")
            # Try to load context if a corresponding file exists
            # base_name = os.path.splitext(os.path.basename(filepath))[0]
            # context_file_path = os.path.join(os.path.dirname(filepath), f"{base_name}_context.txt")
            # try: # Need to handle potential import loop if load_context_file is needed here
            #    from src.data_io import load_context_file 
            #    temp_context = load_context_file(context_file_path) 
            #    if temp_context: self.context_area.insert("1.0", temp_context)
            # except ImportError:
            #    print("Could not import load_context_file here.")
                
        else:
            self.status_var.set("File selection cancelled.")

    def start_processing(self):
        """Starts the data processing pipeline in a separate thread for the current session."""
        if not self.current_input_file:
            messagebox.showerror("Error", "Please select an input file first (use 'Browse...' or 'New Session' then 'Browse...').")
            return

        if self.process_thread and self.process_thread.is_alive():
            messagebox.showwarning("Busy", "Processing is already running.")
            return
            
        # Determine Session ID and Paths
        is_new_session = not self.current_session_id
        if is_new_session:
             self.current_session_id = time.strftime("%Y%m%d_%H%M%S") + "_" + os.path.splitext(os.path.basename(self.current_input_file))[0]
             
        # Get paths based on current_session_id
        session_dir = os.path.abspath(os.path.join(SESSIONS_DIR, self.current_session_id))
        os.makedirs(session_dir, exist_ok=True)
        output_csv = os.path.join(session_dir, "results.csv")
        pipeline_log = os.path.join(session_dir, "pipeline.log")
        scoring_log = os.path.join(session_dir, "scoring.log")

        # Get context and save/update metadata
        current_context = self.context_area.get("1.0", tk.END).strip() or None
        
        # Update metadata
        self.session_metadata = load_session_metadata() # Reload fresh metadata
        session_data = next((s for s in self.session_metadata if s['session_id'] == self.current_session_id), None)
        
        if not session_data: # It's a new session, add entry
            session_data = {
                 "session_id": self.current_session_id,
                 "timestamp_created": time.strftime("%Y-%m-%d %H:%M:%S"),
                 "original_input_file": self.current_input_file,
                 "last_processed_count": 0
            }
            self.session_metadata.append(session_data)
            # Update UI Combobox
            self.session_ids.append(self.current_session_id)
            self.session_combobox['values'] = self.session_ids
            self.selected_session_var.set(self.current_session_id)
        
        # Update status and other fields before saving
        session_data['status'] = 'running'
        session_data['context_used'] = current_context
        session_data['output_csv'] = output_csv 
        session_data['pipeline_log'] = pipeline_log
        session_data['scoring_log'] = scoring_log
        save_session_metadata(self.session_metadata) 
             
        # Disable controls & Update status
        self.disable_controls()
        self.status_var.set(f"Processing session: {self.current_session_id}...")
        self.root.update_idletasks()

        # Clear table for the new run
        self.clear_treeview()
        
        # Write header row immediately 
        save_results_csv([], output_csv, append_mode=False, fieldnames=self.columns)
        
        # Start the pipeline thread
        self.process_thread = threading.Thread(
            target=self.run_pipeline_in_thread,
            args=(self.current_input_file, output_csv, pipeline_log, scoring_log, current_context, self.current_session_id),
            daemon=True
        )
        self.process_thread.start()

    # --- Add Helper Methods for Enabling/Disabling Controls ---
    def disable_controls(self):
        self.start_button.config(state=tk.DISABLED)
        self.browse_button.config(state=tk.DISABLED)
        self.new_session_button.config(state=tk.DISABLED)
        self.session_combobox.config(state=tk.DISABLED)

    def enable_controls(self):
        self.start_button.config(state=tk.NORMAL)
        self.browse_button.config(state=tk.NORMAL)
        self.new_session_button.config(state=tk.NORMAL)
        self.session_combobox.config(state='readonly') # Keep combobox readonly

    # --- Modify run_pipeline_in_thread to accept session_id ---
    def run_pipeline_in_thread(self, input_path, output_path, pipe_log, score_log, context, session_id):
        """Wrapper to run the async pipeline in a separate thread."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            scrapingbee_api_key, openai_api_key, serper_api_key = load_env_vars()
            llm_config = load_llm_config("llm_config.yaml")
            if not all([scrapingbee_api_key, openai_api_key, serper_api_key, llm_config]):
                 raise ValueError("Missing API keys or LLM config in thread.")

            async def main_async_logic():
                openai_client = AsyncOpenAI(api_key=openai_api_key)
                sb_client = ScrapingBeeClient(api_key=scrapingbee_api_key)
                async with aiohttp.ClientSession() as session:
                     success, failed, _ = await run_pipeline_for_file(
                         input_file_path=input_path,
                         output_csv_path=output_path,
                         pipeline_log_path=pipe_log,
                         scoring_log_path=score_log,
                         context_text=context,
                         company_col_index=0, 
                         aiohttp_session=session,
                         sb_client=sb_client,
                         llm_config=llm_config,
                         openai_client=openai_client,
                         serper_api_key=serper_api_key,
                         expected_csv_fieldnames=list(self.columns)
                     )
                     return success, failed

            success_count, failure_count = loop.run_until_complete(main_async_logic())
            self.queue.put(("finished", session_id, success_count, failure_count))
        except Exception as e:
            print(f"ERROR in thread: {e}")
            traceback.print_exc()
            self.queue.put(("error", session_id, str(e)))
        finally:
             loop.close()

    # --- Modify process_queue to handle session_id ---
    def process_queue(self, message):
        """Processes messages received from the worker thread."""
        status_type = message[0]
        session_id_from_thread = message[1] 
        
        # Update metadata regardless of which session is currently viewed
        current_metadata = load_session_metadata()
        session_data = next((s for s in current_metadata if s['session_id'] == session_id_from_thread), None)
        final_status_str = "unknown"
        
        if status_type == "finished":
            success, failed = message[2], message[3]
            final_status_str = f"Completed. Success: {success}, Failed: {failed}."
            if session_data: session_data['status'] = 'completed'; session_data['last_processed_count'] = success+failed
            
            # If the completed session is the one currently selected, auto-load results
            if session_id_from_thread == self.current_session_id:
                self.status_var.set(final_status_str + " Loading results...")
                self.root.update_idletasks()
                if session_data and session_data.get("output_csv"):
                     self.load_results_to_table(session_data["output_csv"])
                self.status_var.set(final_status_str + " Ready.") # Update status after loading
                messagebox.showinfo("Complete", f"Session {session_id_from_thread} finished.\nSuccess: {success}, Failed: {failed}.")
                self.enable_controls()
            else:
                 self.status_var.set(f"Session {session_id_from_thread} finished in background. {final_status_str}")
                 if not (self.process_thread and self.process_thread.is_alive()):
                    self.enable_controls()

        elif status_type == "error":
            error_msg = message[2]
            final_status_str = f"Error: {error_msg}."
            if session_data: session_data['status'] = 'error'
            
            if session_id_from_thread == self.current_session_id:
                 self.status_var.set(f"Error in session {session_id_from_thread}. Ready.")
                 messagebox.showerror("Error", f"Session {session_id_from_thread} failed:\n{error_msg}")
                 self.enable_controls()
            else:
                 self.status_var.set(f"Error in background session {session_id_from_thread}. Ready.")
                 if not (self.process_thread and self.process_thread.is_alive()):
                      self.enable_controls()

        # Save updated metadata
        if session_data:
            save_session_metadata(current_metadata)
        else:
            logging.error(f"Could not find metadata for completed/errored session_id: {session_id_from_thread}")
            if not (self.process_thread and self.process_thread.is_alive()):
                 self.enable_controls()

    # --- Modify open_output_folder for sessions ---
    def open_output_folder(self):
        """Opens the folder for the currently selected session."""
        if not self.current_session_id:
            # Open the base sessions folder if no session is active/selected
            output_dir = os.path.abspath(SESSIONS_DIR)
            if not os.path.exists(output_dir):
                messagebox.showinfo("Info", f"Base sessions folder does not exist yet:\n{output_dir}")
                return
            messagebox.showinfo("Info", "No active session selected. Opening base sessions folder.")
        else:
            output_dir = os.path.abspath(os.path.join(SESSIONS_DIR, self.current_session_id))

        if not os.path.exists(output_dir):
            messagebox.showerror("Error", f"Directory does not exist:\n{output_dir}")
            self.status_var.set("Session directory not found.")
            return
            
        try:
            if os.name == 'nt': # Windows
                os.startfile(output_dir)
            elif sys.platform == 'darwin': # macOS
                subprocess.run(['open', output_dir], check=True)
            else: # Linux and other Unix-like
                subprocess.run(['xdg-open', output_dir], check=True)
            self.status_var.set(f"Opened session folder: {self.current_session_id or 'Base Sessions'}")
        except FileNotFoundError:
             messagebox.showerror("Error", f"Could not open directory (not found):\n{output_dir}")
             self.status_var.set("Error opening session directory.")
        except Exception as e:
            messagebox.showerror("Error", f"Could not open directory:\n{output_dir}\nError: {e}")
            self.status_var.set("Error opening session directory.")

    def clear_treeview(self):
         """Clears all items from the results table."""
         for item in self.tree.get_children():
             self.tree.delete(item)

    def check_queue(self):
        """Checks the queue for messages from the worker thread."""
        try:
            message = self.queue.get_nowait()
            self.process_queue(message)
        except queue.Empty:
            pass
        finally:
            # Reschedule the check
            self.root.after(100, self.check_queue)

if __name__ == "__main__":
    root = tk.Tk()
    app = CompanyApp(root)
    root.mainloop() 