from .base import Event


class PeriodEndEvent(Event):
    """
    Event for when a period ends.
    """

    def parse(self):
        """
        Parse the period-end event and return a formatted message.
        """
        period_number = self.period_number
        period_type = self.event_data.get("periodDescriptor", {}).get("periodType", "unknown")
        period_ordinal = f"{period_number}{'th' if 10 <= period_number % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(period_number % 10, 'th')}"

        if period_type == "REG":
            return f"The {period_ordinal} period has ended."
        elif period_type == "OT":
            return f"Overtime has ended."
        elif period_type == "SO":
            return f"The shootout has ended."
        else:
            return f"The {period_ordinal} period of type '{period_type}' has ended."
