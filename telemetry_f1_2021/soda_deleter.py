import cx_Oracle
from oracledb import OracleJSONDatabaseConnection

dbhandler = OracleJSONDatabaseConnection()

# WARNING: this will delete data from the hackathon!! Only use if you know what you're doing.
'''
created by @jasperan to fix a bug. Code is commented to prevent accidental executions
'''
#dbhandler.delete('f1_2021_weather', 'timestamp', {"$gt": 1642463000})