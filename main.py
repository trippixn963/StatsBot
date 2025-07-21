import os
import signal
import asyncio
import logging
import discord
from src.utils.tree_log import log_run_header, log_run_end, log_error_with_traceback, log_perfect_tree_section
from src.core.bot import OptimizedStatsBot
from dotenv import load_dotenv

# Load environment variables
load_dotenv("config/.env")

# Global variable to track shutdown state
shutdown_event = asyncio.Event()

def handle_shutdown(signum, frame):
    """Handle shutdown signals gracefully."""
    log_perfect_tree_section(
        "Shutdown Signal",
        [
            ("signal", "SIGINT" if signum == signal.SIGINT else "SIGTERM"),
            ("status", "Initiating graceful shutdown")
        ],
        emoji="🛑"
    )
    shutdown_event.set()

async def main():
    try:
        # Start run logging
        log_run_header("StatsBot", "1.0.0")
        
        # Create bot
        from src.core.config import load_config
        config = load_config()
        bot = OptimizedStatsBot(config)
        
        # Set up signal handlers
        signal.signal(signal.SIGINT, handle_shutdown)
        signal.signal(signal.SIGTERM, handle_shutdown)
        
        # Start the bot with reconnect logic
        async with bot:
            # Set up shutdown handler
            bot.shutdown_event = shutdown_event
            
            # Start bot and wait for shutdown signal with improved reconnect handling
            try:
                # Configure Discord's internal reconnect settings
                discord.client._log.setLevel(logging.INFO)
                
                # Log connection attempt
                log_perfect_tree_section(
                    "Bot Connection",
                    [("status", "Connecting to Discord")],
                    emoji="🔌"
                )
                
                # Start with reconnect enabled
                await bot.start(os.getenv('BOT_TOKEN'), reconnect=True)
                
            except discord.errors.LoginFailure as e:
                log_error_with_traceback("Invalid bot token", e, "CRITICAL")
                return
                
            except asyncio.CancelledError:
                # Log graceful shutdown
                log_perfect_tree_section(
                    "Graceful Shutdown",
                    [("status", "Received shutdown signal")],
                    emoji="🔄"
                )
                
            except Exception as e:
                log_error_with_traceback("Connection error", e, "ERROR")
                
            finally:
                # Set shutdown presence
                if hasattr(bot, 'rich_presence_service'):
                    try:
                        await bot.rich_presence_service.set_shutdown_presence()
                    except Exception as e:
                        log_error_with_traceback("Failed to set shutdown presence", e)
                
                # Cancel background tasks
                tasks_to_cancel = []
                if hasattr(bot, 'bg_task'):
                    tasks_to_cancel.append(bot.bg_task)
                if hasattr(bot, 'heartbeat_task'):
                    tasks_to_cancel.append(bot.heartbeat_task)
                if hasattr(bot, 'rich_presence_task'):
                    tasks_to_cancel.append(bot.rich_presence_task)
                
                # Cancel all tasks
                for task in tasks_to_cancel:
                    if not task.done():
                        task.cancel()
                
                # Wait for tasks to complete
                if tasks_to_cancel:
                    try:
                        await asyncio.wait(tasks_to_cancel, timeout=5.0)
                    except asyncio.TimeoutError:
                        log_perfect_tree_section(
                            "Task Cancellation",
                            [("status", "Force cancelled tasks after timeout")],
                            emoji="⚠️"
                        )
                    except Exception as e:
                        log_error_with_traceback("Error cancelling tasks", e)
                
                # Save any pending data
                if hasattr(bot, 'stats_service') and hasattr(bot.stats_service, 'stats_tracker'):
                    try:
                        await bot.stats_service.save_data()
                    except Exception as e:
                        log_error_with_traceback("Failed to save data", e)
                
                # Close connections
                try:
                    await bot.close()
                except Exception as e:
                    log_error_with_traceback("Error closing bot connection", e)
                
                # Log successful shutdown
                log_perfect_tree_section(
                    "Shutdown Complete",
                    [("status", "All data saved and connections closed")],
                    emoji="✅"
                )
        
        # Log normal shutdown
        log_run_end("Normal shutdown")
    except Exception as e:
        # Log critical error with details
        log_perfect_tree_section(
            "Critical Error",
            [
                ("error", str(e)),
                ("type", e.__class__.__name__),
                ("status", "Bot startup failed")
            ],
            emoji="🔥"
        )
        log_error_with_traceback("Bot startup failed", e, "CRITICAL")
        log_run_end(f"Error: {str(e)}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # Log keyboard interrupt
        log_perfect_tree_section(
            "Keyboard Interrupt",
            [("status", "User initiated shutdown")],
            emoji="⌨️"
        )
    except Exception as e:
        # Log unexpected error
        log_perfect_tree_section(
            "Fatal Error",
            [
                ("error", str(e)),
                ("type", e.__class__.__name__),
                ("status", "Unexpected shutdown")
            ],
            emoji="💥"
        )
        log_error_with_traceback("Fatal error", e, "CRITICAL") 