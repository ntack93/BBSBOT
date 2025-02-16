import threading
import asyncio
import telnetlib3
import time
import queue
import re
import curses

class BBSBotCLI:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.current_line = 0
        self.buffer_lines = []
        self.scroll_position = 0  # Add scroll position tracking
        self.init_screen()
        self.host = ""
        self.port = 0
        self.loop = asyncio.new_event_loop()
        self.msg_queue = queue.Queue()
        self.partial_line = ""
        self.connected = False
        self.reader = None
        self.writer = None
        self.get_input("Command: ")  # Add this line to prompt for input immediately

    def init_screen(self):
        curses.use_default_colors()
        curses.start_color()
        self.stdscr.clear()
        height, width = self.stdscr.getmaxyx()
        
        # Create output window with a border and make it scrollable
        self.output_win = curses.newwin(height - 3, width, 0, 0)
        self.input_win = curses.newwin(3, width, height - 3, 0)
        
        # Enable scrolling for both windows
        self.output_win.scrollok(True)
        self.output_win.idlok(True)
        self.input_win.scrollok(True)
        
        # Enable keypad input for scrolling
        self.output_win.keypad(True)
        self.stdscr.keypad(True)
        
        self.max_lines = height - 5
        self.height = height
        self.width = width
        
        # Initialize color pairs
        self.init_colors()
        
        self.refresh_output("CLI interface active. Type 'exit' or 'quit' to leave.")
        self.get_input("Command: ")  # Add this line to prompt for input immediately

    def init_colors(self):
        """Initialize color pairs for ANSI colors"""
        curses.init_pair(1, curses.COLOR_RED, curses.COLOR_BLACK)
        curses.init_pair(2, curses.COLOR_GREEN, curses.COLOR_BLACK)
        curses.init_pair(3, curses.COLOR_YELLOW, curses.COLOR_BLACK)
        curses.init_pair(4, curses.COLOR_BLUE, curses.COLOR_BLACK)
        curses.init_pair(5, curses.COLOR_MAGENTA, curses.COLOR_BLACK)
        curses.init_pair(6, curses.COLOR_CYAN, curses.COLOR_BLACK)
        curses.init_pair(7, curses.COLOR_WHITE, curses.COLOR_BLACK)
        curses.init_pair(8, curses.COLOR_BLACK, curses.COLOR_BLACK)  # Bright black (gray)
        curses.init_pair(9, curses.COLOR_RED, curses.COLOR_BLACK)    # Bright red
        curses.init_pair(10, curses.COLOR_GREEN, curses.COLOR_BLACK) # Bright green
        curses.init_pair(11, curses.COLOR_YELLOW, curses.COLOR_BLACK)# Bright yellow
        curses.init_pair(12, curses.COLOR_BLUE, curses.COLOR_BLACK)  # Bright blue
        curses.init_pair(13, curses.COLOR_MAGENTA, curses.COLOR_BLACK)# Bright magenta
        curses.init_pair(14, curses.COLOR_CYAN, curses.COLOR_BLACK)  # Bright cyan
        curses.init_pair(15, curses.COLOR_WHITE, curses.COLOR_BLACK) # Bright white

    def refresh_output(self, text):
        """Refresh the output window with buffered content"""
        # Add new text to buffer
        if text:
            new_lines = text.split('\n')
            self.buffer_lines.extend(new_lines)
        
        # Keep buffer size manageable
        if len(self.buffer_lines) > 1000:
            self.buffer_lines = self.buffer_lines[-1000:]
        
        # Calculate visible area
        height, width = self.output_win.getmaxyx()
        start_line = max(0, len(self.buffer_lines) - height + 1 + self.scroll_position)
        end_line = min(start_line + height - 1, len(self.buffer_lines))
        
        # Clear and redraw
        self.output_win.clear()
        
        try:
            # Display each line in the visible area
            for i, line in enumerate(self.buffer_lines[start_line:end_line]):
                y_pos = i
                # Ensure we don't write beyond window boundaries
                if y_pos < height:
                    self.output_win.addstr(y_pos, 0, line[:width-1])
        except curses.error:
            pass  # Ignore curses errors from writing at bottom-right corner
        
        self.output_win.refresh()

    def process_incoming_messages(self):
        """Process incoming messages and update display"""
        while True:
            try:
                data = self.msg_queue.get_nowait()
                if data:
                    self.display_data(data)
            except queue.Empty:
                time.sleep(0.1)
            except curses.error:
                continue
            except Exception as e:
                self.display_data(f"Error: {str(e)}\n")

    def get_input(self, prompt):
        """Get input from user with support for scrolling"""
        self.input_win.clear()
        self.input_win.border(0)
        self.input_win.addstr(1, 1, prompt)
        self.input_win.refresh()
        
        curses.echo()
        
        # Handle special keys for scrolling
        while True:
            try:
                key = self.stdscr.getch()
                if key == curses.KEY_UP:
                    self.scroll_position = min(self.scroll_position + 1, len(self.buffer_lines) - self.height + 5)
                    self.refresh_output("")
                    continue
                elif key == curses.KEY_DOWN:
                    self.scroll_position = max(self.scroll_position - 1, 0)
                    self.refresh_output("")
                    continue
                elif key == curses.KEY_PPAGE:  # Page Up
                    self.scroll_position = min(self.scroll_position + self.height - 5, len(self.buffer_lines) - self.height + 5)
                    self.refresh_output("")
                    continue
                elif key == curses.KEY_NPAGE:  # Page Down
                    self.scroll_position = max(self.scroll_position - (self.height - 5), 0)
                    self.refresh_output("")
                    continue
                else:
                    # Normal input handling
                    self.input_win.clear()
                    self.input_win.border(0)
                    self.input_win.addstr(1, 1, prompt)
                    user_input = self.input_win.getstr(1, len(prompt) + 1).decode("utf-8")
                    curses.noecho()
                    return user_input
            except curses.error:
                continue

    def run(self):
        self.host = self.get_input("Enter BBS hostname: ")
        self.port = int(self.get_input("Enter BBS port: "))
        self.refresh_output(f"Connecting to {self.host}:{self.port}...")
        self.start_connection()

        while True:
            try:
                cmd = self.get_input("Command: ")
                self.refresh_output("> " + cmd)
                if cmd.strip().lower() in ['exit', 'quit']:
                    break
                if self.connected and self.writer:
                    asyncio.run_coroutine_threadsafe(self._send_message(cmd + "\r\n"), self.loop)
            except KeyboardInterrupt:
                self.refresh_output("Exiting...")
                break

    def start_connection(self):
        """Start the telnetlib3 client in a background thread."""
        self.stop_event = threading.Event()

        def run_telnet():
            asyncio.set_event_loop(self.loop)
            self.loop.run_until_complete(self.telnet_client_task(self.host, self.port))

        thread = threading.Thread(target=run_telnet, daemon=True)
        thread.start()

        # Start a separate thread to process incoming messages
        threading.Thread(target=self.process_incoming_messages, daemon=True).start()

    async def telnet_client_task(self, host, port):
        """Async function connecting via telnetlib3 (CP437 + ANSI), reading bigger chunks."""
        try:
            reader, writer = await telnetlib3.open_connection(
                host=host,
                port=port,
                term='ansi',
                encoding='cp437',
                cols=136  # Set terminal width to 136 columns
            )
        except Exception as e:
            self.msg_queue.put_nowait(f"Connection failed: {e}\n")
            return

        self.reader = reader
        self.writer = writer
        self.connected = True
        self.msg_queue.put_nowait(f"Connected to {host}:{port}\n")

        try:
            while not self.stop_event.is_set():
                data = await reader.read(4096)
                if not data:
                    break
                self.msg_queue.put_nowait(data)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.msg_queue.put_nowait(f"Error reading from server: {e}\n")
        finally:
            await self.disconnect_from_bbs()

    async def disconnect_from_bbs(self):
        """Stop the background thread and close connections."""
        if not self.connected:
            return

        self.stop_event.set()
        if self.writer:
            try:
                self.writer.close()
                await self.writer.drain()  # Ensure the writer is closed properly
            except Exception as e:
                print(f"Error closing writer: {e}")

        self.connected = False
        self.reader = None
        self.writer = None
        self.msg_queue.put_nowait("Disconnected from BBS.\n")

    def display_data(self, data):
        """Display data with extended ASCII and ANSI parsing."""
        try:
            # Split data into lines while preserving ANSI codes
            lines = data.replace('\r\n', '\n').replace('\r', '\n').split('\n')
            
            for line in lines:
                if not line:
                    continue
                    
                # Process the line character by character
                current_x = 0
                current_attr = curses.color_pair(7)  # Default to white
                
                i = 0
                while i < len(line):
                    if line[i:i+2] == '^[' or line[i:i+2] == '\x1b[':
                        # Found an ANSI escape sequence
                        end_marker = line.find('m', i)
                        if end_marker != -1:
                            # Extract the color codes
                            codes = line[i+2:end_marker].split(';')
                            for code in codes:
                                if code == '0':
                                    current_attr = curses.color_pair(7)
                                elif code in ['30', '31', '32', '33', '34', '35', '36', '37',
                                            '90', '91', '92', '93', '94', '95', '96', '97']:
                                    current_attr = self.map_code_to_color_pair(code)
                            i = end_marker + 1
                            continue
                    
                    # Print the character with current attributes
                    try:
                        self.output_win.addstr(self.current_line, current_x, line[i], current_attr)
                    except curses.error:
                        pass  # Ignore errors from writing at screen edges
                    current_x += 1
                    i += 1
                
                # Move to next line
                self.current_line += 1
                if self.current_line >= self.height - 3:  # Leave room for input
                    self.output_win.scroll()
                    self.current_line = self.height - 4
            
            self.output_win.refresh()
        
        except Exception as e:
            # Fall back to simple display if something goes wrong
            try:
                self.output_win.addstr(str(data))
                self.output_win.refresh()
            except curses.error:
                pass

    def map_code_to_color_pair(self, color_code):
        """Map a numeric color code to a curses color pair."""
        color_map = {
            '30': curses.color_pair(8) | curses.A_DIM,     # Black
            '31': curses.color_pair(1),                     # Red
            '32': curses.color_pair(2),                     # Green
            '33': curses.color_pair(3),                     # Yellow
            '34': curses.color_pair(4),                     # Blue
            '35': curses.color_pair(5),                     # Magenta
            '36': curses.color_pair(6),                     # Cyan
            '37': curses.color_pair(7),                     # White
            '90': curses.color_pair(8) | curses.A_BOLD,    # Bright Black
            '91': curses.color_pair(1) | curses.A_BOLD,    # Bright Red
            '92': curses.color_pair(2) | curses.A_BOLD,    # Bright Green
            '93': curses.color_pair(3) | curses.A_BOLD,    # Bright Yellow
            '94': curses.color_pair(4) | curses.A_BOLD,    # Bright Blue
            '95': curses.color_pair(5) | curses.A_BOLD,    # Bright Magenta
            '96': curses.color_pair(6) | curses.A_BOLD,    # Bright Cyan
            '97': curses.color_pair(7) | curses.A_BOLD,    # Bright White
        }
        return color_map.get(color_code, curses.color_pair(7))

    async def _send_message(self, message):
        """Coroutine to send a message."""
        self.writer.write(message)
        await self.writer.drain()

def main_cli(stdscr):
    curses.start_color()
    curses.init_pair(1, curses.COLOR_RED, curses.COLOR_BLACK)
    curses.init_pair(2, curses.COLOR_GREEN, curses.COLOR_BLACK)
    curses.init_pair(3, curses.COLOR_YELLOW, curses.COLOR_BLACK)
    curses.init_pair(4, curses.COLOR_BLUE, curses.COLOR_BLACK)
    curses.init_pair(5, curses.COLOR_MAGENTA, curses.COLOR_BLACK)
    curses.init_pair(6, curses.COLOR_CYAN, curses.COLOR_BLACK)
    curses.init_pair(7, curses.COLOR_WHITE, curses.COLOR_BLACK)
    curses.init_pair(8, curses.COLOR_BLACK, curses.COLOR_BLACK)  # Bright black (gray)
    curses.init_pair(9, curses.COLOR_RED, curses.COLOR_BLACK)    # Bright red
    curses.init_pair(10, curses.COLOR_GREEN, curses.COLOR_BLACK) # Bright green
    curses.init_pair(11, curses.COLOR_YELLOW, curses.COLOR_BLACK)# Bright yellow
    curses.init_pair(12, curses.COLOR_BLUE, curses.COLOR_BLACK)  # Bright blue
    curses.init_pair(13, curses.COLOR_MAGENTA, curses.COLOR_BLACK)# Bright magenta
    curses.init_pair(14, curses.COLOR_CYAN, curses.COLOR_BLACK)  # Bright cyan
    curses.init_pair(15, curses.COLOR_WHITE, curses.COLOR_BLACK) # Bright white
    cli = BBSBotCLI(stdscr)
    cli.run()

def main():
    curses.wrapper(main_cli)

if __name__ == "__main__":
    main()
