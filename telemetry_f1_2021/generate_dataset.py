from oracledb import OracleJSONDatabaseConnection
import json

'''
This file creates a collection, retrieves all elements from it, and saves it into weather.json
'''

jsondb = OracleJSONDatabaseConnection()

connection = jsondb.get_connection()
connection.autocommit = True
soda = connection.getSodaDatabase()
x_collection = soda.createCollection('f1_2021_weather')

all_data = []
for doc in x_collection.find().getCursor():
    content = doc.getContent()
    all_data.append(content)

print(f'Data length: {len(all_data)}')

with open("weather.json", 'w') as outfile:
    outfile.write(json.dumps(all_data, indent=4))

outfile.close()
