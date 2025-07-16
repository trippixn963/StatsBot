import json
from datetime import datetime, timedelta
from pathlib import Path
import pytz
from typing import Dict, List, Optional
from src.utils.tree_log import log_perfect_tree_section, log_error_with_traceback

class StatsTracker:
    def __init__(self):
        self.est_tz = pytz.timezone('US/Eastern')
        self.data_dir = Path("data")
        self.data_dir.mkdir(exist_ok=True)
        self.stats_file = self.data_dir / "member_stats.json"
        self.daily_stats: Dict[str, dict] = self._load_stats()
        
        # Initialize empty stats for today if needed
        current_date = datetime.now(self.est_tz).strftime("%Y-%m-%d")
        if current_date not in self.daily_stats:
            self.daily_stats[current_date] = {
                "joins": [],
                "leaves": [],
                "bans": []
            }
        
        # Log initialization
        log_perfect_tree_section(
            "Stats Tracker",
            [
                ("status", "Initializing"),
                ("data_file", str(self.stats_file)),
                ("timezone", "EST")
            ],
            emoji="📊"
        )
    
    def _load_stats(self) -> Dict[str, dict]:
        """Load stats from JSON file."""
        if self.stats_file.exists():
            try:
                with open(self.stats_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                log_error_with_traceback("Failed to load stats file", e, "ERROR")
                return {}
        return {}
    
    def _save_stats(self):
        """Save stats to file."""
        try:
            with open(self.stats_file, 'w') as f:
                json.dump(self.daily_stats, f, indent=4)
        except Exception as e:
            log_error_with_traceback("Failed to save stats file", e, "ERROR")

    async def save_data(self):
        """Save all pending data before shutdown."""
        log_perfect_tree_section(
            "Saving Stats Data",
            [
                ("status", "Saving data before shutdown"),
                ("data_file", str(self.stats_file))
            ],
            emoji="��"
        )
        try:
            with open(self.stats_file, 'w') as f:
                json.dump(self.daily_stats, f, indent=4)
            log_perfect_tree_section(
                "Stats Data Saved",
                [
                    ("status", "Data saved successfully"),
                    ("data_file", str(self.stats_file))
                ],
                emoji="✅"
            )
        except Exception as e:
            log_error_with_traceback("Failed to save stats file", e, "ERROR")
            log_perfect_tree_section(
                "Stats Data Save Failed",
                [
                    ("status", "Failed to save data"),
                    ("data_file", str(self.stats_file)),
                    ("error", str(e))
                ],
                emoji="❌"
            )
    
    def record_member_join(self, member_id: int, username: str):
        """Record a member join event."""
        current_date = datetime.now(self.est_tz).strftime("%Y-%m-%d")
        
        if current_date not in self.daily_stats:
            self.daily_stats[current_date] = {
                "joins": [],
                "leaves": []
            }
        
        self.daily_stats[current_date]["joins"].append({
            "id": member_id,
            "username": username,
            "timestamp": datetime.now(self.est_tz).isoformat()
        })
        self._save_stats()
        
        # Log the join
        log_perfect_tree_section(
            "Member Join",
            [
                ("member", username),
                ("id", str(member_id)),
                ("date", current_date)
            ],
            emoji="➡️"
        )
    
    def record_member_leave(self, member_id: int, username: str):
        """Record a member leave event."""
        current_date = datetime.now(self.est_tz).strftime("%Y-%m-%d")
        
        if current_date not in self.daily_stats:
            self.daily_stats[current_date] = {
                "joins": [],
                "leaves": []
            }
        
        self.daily_stats[current_date]["leaves"].append({
            "id": member_id,
            "username": username,
            "timestamp": datetime.now(self.est_tz).isoformat()
        })
        self._save_stats()
        
        # Log the leave
        log_perfect_tree_section(
            "Member Leave",
            [
                ("member", username),
                ("id", str(member_id)),
                ("date", current_date)
            ],
            emoji="⬅️"
        )
    
    def record_member_ban(self, member_id: int, username: str):
        """Record a member ban event."""
        current_date = datetime.now(self.est_tz).strftime("%Y-%m-%d")
        
        if current_date not in self.daily_stats:
            self.daily_stats[current_date] = {
                "joins": [],
                "leaves": [],
                "bans": []
            }
        
        self.daily_stats[current_date]["bans"].append({
            "id": member_id,
            "username": username,
            "timestamp": datetime.now(self.est_tz).isoformat()
        })
        self._save_stats()
        
        # Log the ban
        log_perfect_tree_section(
            "Member Ban",
            [
                ("member", username),
                ("id", str(member_id)),
                ("date", current_date)
            ],
            emoji="🔨"
        )

    def get_daily_stats(self, date: Optional[str] = None) -> dict:
        """Get stats for a specific date or today."""
        if date is None:
            date = datetime.now(self.est_tz).strftime("%Y-%m-%d")
            
        if date in self.daily_stats:
            stats = self.daily_stats[date]
            return {
                "date": date,
                "joins": len(stats["joins"]),
                "leaves": len(stats["leaves"]),
                "bans": len(stats.get("bans", [])),  # Handle cases where bans key might not exist in older data
                "net_change": len(stats["joins"]) - len(stats["leaves"]),
                "join_list": stats["joins"],
                "leave_list": stats["leaves"],
                "ban_list": stats.get("bans", [])  # Handle cases where bans key might not exist in older data
            }
        return {
            "date": date,
            "joins": 0,
            "leaves": 0,
            "bans": 0,
            "net_change": 0,
            "join_list": [],
            "leave_list": [],
            "ban_list": []
        }
    
    def get_weekly_stats(self) -> dict:
        """Get stats for the past week."""
        end_date = datetime.now(self.est_tz)
        start_date = end_date - timedelta(days=7)
        
        weekly_stats = {
            "total_joins": 0,
            "total_leaves": 0,
            "total_bans": 0,
            "net_change": 0,
            "daily_breakdown": [],
            "most_active_day": None,
            "join_list": [],
            "leave_list": [],
            "ban_list": []
        }
        
        max_activity = 0
        current_date = start_date
        
        while current_date <= end_date:
            date_str = current_date.strftime("%Y-%m-%d")
            daily_stats = self.get_daily_stats(date_str)
            
            weekly_stats["total_joins"] += daily_stats["joins"]
            weekly_stats["total_leaves"] += daily_stats["leaves"]
            weekly_stats["total_bans"] += daily_stats["bans"]
            
            daily_activity = daily_stats["joins"] + daily_stats["leaves"] + daily_stats["bans"]
            if daily_activity > max_activity:
                max_activity = daily_activity
                weekly_stats["most_active_day"] = {
                    "date": date_str,
                    "joins": daily_stats["joins"],
                    "leaves": daily_stats["leaves"],
                    "bans": daily_stats["bans"],
                    "total_activity": daily_activity
                }
            
            weekly_stats["daily_breakdown"].append({
                "date": date_str,
                "joins": daily_stats["joins"],
                "leaves": daily_stats["leaves"],
                "bans": daily_stats["bans"],
                "net_change": daily_stats["net_change"]
            })
            
            if date_str in self.daily_stats:
                weekly_stats["join_list"].extend(self.daily_stats[date_str]["joins"])
                weekly_stats["leave_list"].extend(self.daily_stats[date_str]["leaves"])
                if "bans" in self.daily_stats[date_str]:
                    weekly_stats["ban_list"].extend(self.daily_stats[date_str]["bans"])
            
            current_date += timedelta(days=1)
        
        weekly_stats["net_change"] = weekly_stats["total_joins"] - weekly_stats["total_leaves"]
        return weekly_stats 