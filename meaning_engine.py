import pandas as pd
from datetime import datetime, timedelta

class KnowledgeEngine:
    def __init__(self, raw_path, semantic_path):
        self.raw_path      = raw_path
        self.semantic_path = semantic_path

    def load_recent(self, window_minutes=60):
        df = pd.read_csv(self.raw_path, parse_dates=['timestamp'])
        cutoff = datetime.now() - timedelta(minutes=window_minutes)
        return df[df.timestamp >= cutoff]

    def detect_procrastination(self, df):
        """Find work→YouTube patterns in the last hour."""
        sem_events = []
        # example: find any row with app_usage for a writing app ≥900s
        work = df[df['details'].str.contains('Writer') & df['details'].str.split('|').str[1].astype(int).ge(900)]
        yt   = df[df['details'].str.contains('YouTube') & df['details'].str.split('|').str[1].astype(int).ge(600)]
        # if any yt timestamp follows a work timestamp
        for _, w in work.iterrows():
            y = yt[yt.timestamp > w.timestamp]
            if not y.empty:
                sem_events.append({
                    'timestamp': y.iloc[0].timestamp,
                    'event':     'procrastination_avoidance',
                    'details':   f"{w['details']}→{y.iloc[0]['details']}"
                })
        return sem_events

    def detect_hyper_responsivity(self, df):
        """Count switches per hour."""
        switches = df[df.event=='app_switch']
        if len(switches) >= 20:
            return [{
                'timestamp': switches.timestamp.max(),
                'event':     'hyper_responsivity',
                'details':   f"{len(switches)} switches in window"
            }]
        return []

    def run(self):
        df = self.load_recent(60)
        sem = []
        sem += self.detect_procrastination(df)
        sem += self.detect_hyper_responsivity(df)
        # ... add more detectors here ...

        # append to semantic log
        sem_df = pd.DataFrame(sem)
        sem_df.to_csv(self.semantic_path, mode='a', header=False, index=False)

if __name__ == "__main__":
    ke = KnowledgeEngine('data/behavior_log.csv', 'data/semantic_log.csv')
    ke.run()
