import os
from pathlib import Path
from dotenv import load_dotenv
import oracledb
import yaml

load_dotenv()

home = str(Path.home())

oracledb_user = os.getenv("DB_USER")
oracledb_password = os.getenv("DB_PASSWORD")
oracledb_connection_string = os.getenv("CONNECTION_STRING")
instant_client_lib_dir = os.getenv("INSTANT_CLIENT_LIB_DIR")

def process_yaml():
	with open("../config.yaml") as file:
		return yaml.safe_load(file)


class OracleJSONDatabaseThinConnection():
    def __init__(self, authentication_mode):
        if authentication_mode == 'cloudshell':
            self.pool = oracledb.create_pool(user=oracledb_user, password=oracledb_password, dsn=oracledb_connection_string,
                                            min=1, max=4, increment=1, getmode=oracledb.POOL_GETMODE_WAIT)
        elif authentication_mode == 'configfile':
            data = process_yaml()
            self.pool = oracledb.create_pool(user=data['db']['username'], password=data['db']['password'], dsn=data['db']['dsn'],
                                            min=1, max=4, increment=1, getmode=oracledb.POOL_GETMODE_WAIT)

        print('Connection successful.')

    def close_pool(self):
        self.pool.close()
        print('Connection pool closed.')

    def insert(self, collection_name, json_object_to_insert):
        connection = self.pool.acquire()
        connection.autocommit = True
        soda = connection.getSodaDatabase()
        x_collection = soda.createCollection(collection_name)

        try:
            x_collection.insertOne(json_object_to_insert)
            print('[DBG] INSERT {} OK'.format(json_object_to_insert))
        except oracledb.IntegrityError as e:
            print('[DBG] INSERT {} ERR: {} '.format(json_object_to_insert, e))
            return -1
        self.pool.release(connection)
        return 1

    def delete(self, collection_name, on_column, on_value):
        connection = self.pool.acquire()
        connection.autocommit = True
        soda = connection.getSodaDatabase()
        x_collection = soda.createCollection(collection_name)
        qbe = {on_column: on_value}
        x_collection.find().filter(qbe).remove()
        self.pool.release(connection)

    def get_connection(self):
        connection = self.pool.acquire()
        connection.autocommit = True
        return connection

    def close_connection(self, conn_object):
        self.pool.release(conn_object)

    def get_collection_names(self):
        connection = self.pool.acquire()
        connection.autocommit = True
        returning_object = connection.getSodaDatabase(
        ).getCollectionNames(startName=None, limit=0)
        self.pool.release(connection)
        return returning_object

    def open_collection(self, collection_name):
        connection = self.pool.acquire()
        returning_object = self.pool.acquire(
        ).getSodaDatabase().openCollection(collection_name)
        self.pool.release(connection)
        return returning_object


class OracleJSONDatabaseThickConnection():
    def __init__(self, authentication_mode):
    
        # You must always call init_oracle_client() to use thick mode in any platform
        if authentication_mode == 'cloudshell':
            self.pool = oracledb.create_pool(user=oracledb_user, password=oracledb_password, dsn=oracledb_connection_string,
                                            min=1, max=4, increment=1, getmode=oracledb.POOL_GETMODE_WAIT)
            oracledb.init_oracle_client(lib_dir=instant_client_lib_dir)
        elif authentication_mode == 'configfile':
            data = process_yaml()
            self.pool = oracledb.create_pool(user=data['db']['username'], password=data['db']['password'], dsn=data['db']['dsn'],
                                            min=1, max=4, increment=1, getmode=oracledb.POOL_GETMODE_WAIT)
            oracledb.init_oracle_client(lib_dir=data['db']['lib_dir'])



    def close_pool(self):
        self.pool.close()
        print('Connection pool closed.')


    def insert(self, collection_name, json_object_to_insert):
        connection = self.pool.acquire()
        connection.autocommit = True
        soda = connection.getSodaDatabase()
        x_collection = soda.createCollection(collection_name)

        try:
            x_collection.insertOne(json_object_to_insert)
            print('[DBG] INSERT {} OK'.format(json_object_to_insert))
        except oracledb.IntegrityError as e:
            print('[DBG] INSERT {} ERR: {} '.format(json_object_to_insert, e))
            return -1
        self.pool.release(connection)
        return 1


    def delete(self, collection_name, on_column, on_value):
        connection = self.pool.acquire()
        connection.autocommit = True
        soda = connection.getSodaDatabase()
        x_collection = soda.createCollection(collection_name)
        qbe = {on_column: on_value}
        x_collection.find().filter(qbe).remove()
        self.pool.release(connection)

    def get_connection(self):
        connection = self.pool.acquire()
        connection.autocommit = True
        return connection

    def close_connection(self, conn_object):
        self.pool.release(conn_object)

    def get_collection_names(self):
        connection = self.pool.acquire()
        connection.autocommit = True
        returning_object = connection.getSodaDatabase(
        ).getCollectionNames(startName=None, limit=0)
        self.pool.release(connection)
        return returning_object

    def open_collection(self, collection_name):
        connection = self.pool.acquire()
        returning_object = self.pool.acquire(
        ).getSodaDatabase().openCollection(collection_name)
        self.pool.release(connection)
        return returning_object


def test_class():
    object = OracleJSONDatabaseThickConnection()
    print(object.pool)
    object.close_pool()


if __name__ == '__main__':
    test_class()
