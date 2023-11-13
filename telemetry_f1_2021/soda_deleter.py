import cx_Oracle
from oracledb import OracleJSONDatabaseConnection

dbhandler = OracleJSONDatabaseConnection()

# WARNING: this is NUCLEAR code! Only use if you know what you're doing.
'''
Code is commented to prevent accidental executions
'''
# dbhandler.delete('f1_2021_weather', 'timestamp', {"$gt": 1642463000})
