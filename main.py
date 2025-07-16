import os
import signal
import asyncio
import discord
from src.utils.tree_log import log_run_header, log_run_end, log_error_with_traceback, log_perfect_tree_section
from src.services.stats import StatsBot
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
        bot = StatsBot()
        
        # Set up signal handlers
        signal.signal(signal.SIGINT, handle_shutdown)
        signal.signal(signal.SIGTERM, handle_shutdown)
        
        # Start the bot
        async with bot:
            # Set up shutdown handler
            bot.shutdown_event = shutdown_event
            
            # Start bot and wait for shutdown signal
            try:
                await bot.start(os.getenv('BOT_TOKEN'))
            except asyncio.CancelledError:
                # Log graceful shutdown
                log_perfect_tree_section(
                    "Graceful Shutdown",
                    [("status", "Received shutdown signal")],
                    emoji="🔄"
                )
            finally:
                # Set shutdown presence
                if hasattr(bot, 'rich_presence_service'):
                    await bot.rich_presence_service.set_shutdown_presence()
                
                # Cancel background tasks
                if hasattr(bot, 'bg_task'):
                    bot.bg_task.cancel()
                if hasattr(bot, 'heartbeat_task'):
                    bot.heartbeat_task.cancel()
                if hasattr(bot, 'rich_presence_task'):
                    bot.rich_presence_task.cancel()
                
                # Wait for tasks to complete
                try:
                    if hasattr(bot, 'bg_task'):
                        await asyncio.wait_for(bot.bg_task, timeout=5.0)
                    if hasattr(bot, 'heartbeat_task'):
                        await asyncio.wait_for(bot.heartbeat_task, timeout=5.0)
                    if hasattr(bot, 'rich_presence_task'):
                        await asyncio.wait_for(bot.rich_presence_task, timeout=5.0)
                except asyncio.TimeoutError:
                    log_perfect_tree_section(
                        "Task Cancellation",
                        [("status", "Force cancelled tasks after timeout")],
                        emoji="⚠️"
                    )
                except Exception as e:
                    log_error_with_traceback("Error cancelling tasks", e)
                
                # Save any pending data
                if hasattr(bot, 'stats_tracker'):
                    await bot.stats_tracker.save_data()
                
                # Close connections
                await bot.close()
                
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