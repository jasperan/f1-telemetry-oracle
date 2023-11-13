from oracledb import OracleJSONDatabaseConnection

'''
Retrieve number of records in the f1_2021_weather collection
'''

dbhandler = OracleJSONDatabaseConnection()

dbhandler.get_count('f1_2021_weather')

dbhandler.close_pool()
