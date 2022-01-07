from oracledb import OracleJSONDatabaseConnection

dbhandler = OracleJSONDatabaseConnection()

dbhandler.get_count('f1_2021_weather')

dbhandler.close_pool()