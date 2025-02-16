# debug_imports.py
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

logger.debug("Starting import test...")

try:
    logger.debug("Importing package...")
    import new_england_listings
    logger.debug("Package imported successfully")

    logger.debug("Testing process_listing...")
    result = new_england_listings.process_listing(
        "https://www.realtor.com/realestateandhomes-detail/17-Shelly-Dr_Derry_NH_03038_M39936-15288",
        use_notion=False
    )
    logger.debug("Process listing successful")
    print(result)

except Exception as e:
    logger.error(f"Error occurred: {str(e)}", exc_info=True)
