from pydantic import BaseModel, Field, PrivateAttr, computed_field
from pydantic.types import List, Annotated
from pydantic.networks import IPv4Address
from datetime import datetime
from uuid import uuid4, UUID
import shutil
import logging

log = logging.getLogger(__name__)
logging.basicConfig(filename="ssoh.log", format='%(asctime)s | %(name)s | %(levelname)s | %(message)s',
                    level=logging.INFO)

log.addHandler(logging.StreamHandler())


class PingEvent(BaseModel):
    """
    PingEvent represents a single instance where the application pinged one target

    Attributes:
        event_uuid: A UUID4 representing one single event. Generated automatically
        timestamp: The timestamp when the ping occurred
        ping: ping in ms
        failure: shows if ping failed
    """
    event_uuid: str = Field(default_factory=lambda: uuid4().hex)
    timestamp: datetime
    ping: float = Field(ge=0)
    failure: bool = Field(default=True)


class PingList(BaseModel):
    """
    PingList is a collection of PingEvent objects for a specific ip address

    Attributes:
        pings: List of PingEvent objects
        target: target ip address

    """
    pings: List[PingEvent] = Field(default=[])
    target: IPv4Address

    def add_ping_event(self, ping: PingEvent):
        """
        Adds a PingEvent to the PingList

        Args:
            ping: a fully instantiated PingEvent object
        """
        # check if ping already exists in list
        for existing_ping in self.pings:
            if existing_ping.event_uuid == ping.event_uuid:
                log.warning(f"Ping already exists for {ping.event_uuid}. Not adding Ping")
                return
        # sort pings based on timestamp
        self.pings.sort(key=lambda sorted_ping: ping.timestamp)
        # delete pings more than 4
        while len(self.pings) >= 5:
            self.pings.pop(0)
        # append new ping
        self.pings.append(ping)

    def add_ping(self, failure: bool, latency: float = 9999999, timestamp=datetime.now()):
        """
        Creates a PingEvent based on ping details and appends it to the PingList

        Args:
            failure: boolean indicating wether the ping failed
            latency: latency of the ping
            timestamp: timestamp of the ping
        """
        self.add_ping_event(PingEvent(timestamp=timestamp, target=self.target, ping=latency, failure=failure))

    def get_valid_percentage(self) -> float:
        """
        Calculates the percentage of valid pings

        Returns:
             a simple float between 0 and 1 indicating the percentage of valid pings
             if no pings were found the percentage is 1.0 (100%)
        """
        # get count of PingEvents where failure is False
        valid_events = sum(not ping.failure for ping in self.pings)
        # prevent zero division
        if len(self.pings) == 0:
            return 1
        return valid_events / len(self.pings)

    @classmethod
    def load(cls, ip: IPv4Address):
        """
        Loads a PingList from a json File based on the ip address
        automatically instantiates an empty instance of the PingList if it doesn't exist

        Args:
            ip: ip address of the PingList to load
        Returns:
            an instance of the PingList class representing the last ping events for the given ip
        """
        filename = str(ip) + ".json"
        try:
            with open(filename, "r") as listfile:
                return cls.model_validate_json(listfile.read())

        except FileNotFoundError:
            log.error("File %s not found or not readable. Creating empty pinglist instead.", filename)
            return cls(target=ip)
        except ValueError:
            backup_file_name: str = filename + "." + str(int(datetime.timestamp(datetime.now())))
            # backup old file to [oldfilename].[timestamp]
            shutil.move(filename, backup_file_name)
            log.error("Invalid JSON. Creating empty pinglist instead. Old file moved to %s", backup_file_name)
            return cls(target=ip)

    @classmethod
    def clear(cls, ip: IPv4Address):
        """
        Clears the PingList from a json File based on the ip and saves it
        Args:
             ip: ip address of the PingList to clear
        """
        this_pinglist = cls.load(ip)
        this_pinglist.pings = []
        log.info(f"Cleared pings on {this_pinglist.target}")
        filename = str(ip) + ".json"
        backup_file_name: str = filename + "." + str(int(datetime.timestamp(datetime.now())))
        log.debug(f"Moving {filename} to {backup_file_name}")
        # backup old file to [oldfilename].[timestamp]
        shutil.move(filename, backup_file_name)
        this_pinglist.save()

    def save(self):
        """
        Saves the current instance of the PingList to a json file named with the target ip
        """
        filename = str(self.target) + ".json"
        with open(filename, "w+") as listfile:
            listfile.write(self.model_dump_json())
