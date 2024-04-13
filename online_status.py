import datetime
import json
from json import JSONDecodeError

from requests.auth import HTTPBasicAuth

from data_models import PingList
from pydantic.networks import IPv4Address
import ping3
from yaml import safe_load
import requests
import logging

# change ping3 to use exceptions instead of different values
ping3.EXCEPTIONS = True


log = logging.getLogger(__name__)
logging.basicConfig(filename="ssoh.log", format='%(asctime)s | %(name)s | %(levelname)s | %(message)s',
                    level=logging.INFO)
config = safe_load(open('config.yml', "r"))
loglevel = getattr(logging, config['loglevel'].upper())

if isinstance(loglevel, int):
    log.level = loglevel

log.addHandler(logging.StreamHandler())


def ping_wrapper(ip: IPv4Address) -> tuple[bool, float]:
    """
    Pings the given IP address and returns a simplified version of the ping3 result

    Args:
        ip: ip address to ping

    Returns:
        A tuple of a boolean and a float
        the boolean indicating whether the ping failed - failed = True - success = False
        the float represents the time elapsed in ms
    """
    try:
        ping = ping3.ping(str(ip), timeout=2, unit="ms")
        log.debug(f"Pinged to {ip} was successful. Ping: {ping}ms")
        return False, ping
    # all ping3 errors inherit from PingError, so we are capturing all errors
    except ping3.errors.PingError as e:
        log.error(f"Ping to {str(ip)} failed. Error: {str(e)}")
        return True, 99999999


def check_ip(ip: IPv4Address):
    """
    Checks if the given IP address is reachable and writes the ping result to the according PingList

    Args:
        ip: ip address to ping
    """
    pinglist = PingList.load(ip)
    failed, latency = ping_wrapper(ip)
    pinglist.add_ping(latency=latency, failure=failed)
    pinglist.save()


def check_all_ips():
    """
    Checks all IP addresses given in config file
    """
    for ip in config["check_ips"]["local"]:
        check_ip(ip)
    for ip in config["check_ips"]["global"]:
        check_ip(ip)


def get_failed_ips() -> dict:
    """
    Returns a dictionary with all the ip addresses that failed the last tests

    Returns:
         dict: dictionary with all the ip addresses that failed the last tests.
         the dict is seperated in local and global ips
    """
    failed = {
        "local": [],
        "global": []
    }
    for ip in config["check_ips"]["local"]:
        pinglist = PingList.load(ip)
        if pinglist.get_valid_percentage() < 0.5:
            failed["local"].append(ip)
    for ip in config["check_ips"]["global"]:
        pinglist = PingList.load(ip)
        if pinglist.get_valid_percentage() < 0.5:
            failed["global"].append(ip)
    return failed


def reset_opnsense():
    """
    Resets the opnsense using the redfish api
    """
    # check if restart is disabled through config
    if config["no_restart"]:
        log.warning("no_restart is true, not restarting")
        return
    try:
        # check if since last reset enough time to satisfy the delay has passed
        with open("lastreset.json", "r") as lastresetfile:
            log.debug("Loading last reset time from lastreset.json")
            lastreset = json.load(lastresetfile)
            log.debug(f"Last reset was at {lastreset}")
            difference = datetime.datetime.now() - datetime.datetime.fromtimestamp(lastreset)
            if difference < datetime.timedelta(minutes=config["reset_delay"]):
                log.info(
                    f"Last reset was only {difference.total_seconds()} seconds ago (Less than {config['reset_delay']} Minutes). Skipping Reset.")
                return
    except FileNotFoundError:
        log.debug("Could not get last reset time from lastreset.json. File does not exist.")
        pass
    except JSONDecodeError:
        log.debug("Could not parse JSON from lastreset.json. File does not exist.")
        pass

    ipmi_details = config["opnsense_ipmi"]
    # load redfish credentials from login.yml
    user_details = safe_load(open("login.yml", "r"))
    # make request to redfish api to Restart the server
    resp: requests.Response = requests.post(
        f"{ipmi_details['protocol']}://{ipmi_details['ip']}:{ipmi_details['port']}/redfish/v1/Systems/Self/Actions/ComputerSystem.Reset",
        json={"ResetType": ipmi_details["reset_type"]}, verify=False,
        auth=HTTPBasicAuth(username=user_details['user'], password=user_details['password']))
    if resp.status_code > 299:
        log.error("Could not reset opnsense successfully.")
        log.info("Reason: " + resp.text)
    else:
        clear_all_ips()
        json.dump(datetime.datetime.timestamp(datetime.datetime.now()), open("lastreset.json", "w"))
        log.debug("Wrote current timestamp to lastreset.json")
    log.debug("Got Response from IPMI: " + str(resp.json()))


def clear_all_ips():
    log.debug("Clearing all IPs")
    for ip in config["check_ips"]["local"]:
        log.debug("Clearing IP: " + ip)
        PingList.clear(IPv4Address(ip))
    for ip in config["check_ips"]["global"]:
        log.debug("Clearing IP: " + ip)
        PingList.clear(IPv4Address(ip))


if __name__ == '__main__':
    check_all_ips()
    failed_ips = get_failed_ips()
    if len(failed_ips["global"]) > 0 and len(failed_ips["local"]) > 0:
        log.error("At least one global and one local ip failed. Restarting OPNSense...")
        reset_opnsense()
        exit(0)
    if len(failed_ips["global"]) > 0.5 * len(config["check_ips"]["global"]):
        log.error("More than half of all global ips failed. Restarting OPNSense...")
        reset_opnsense()
        exit(0)
    if len(failed_ips["local"]) > 0.5 * len(config["check_ips"]["local"]):
        log.error("More than half of all local ips failed. Restarting OPNSense...")
        reset_opnsense()
        exit(0)
    log.info(f"Script ran successfully! No IPs failed.")
