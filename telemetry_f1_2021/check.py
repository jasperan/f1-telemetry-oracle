# Copyright (c) 2022 Oracle and/or its affiliates.

import os
import oracledb
from dotenv import load_dotenv
from colors import color

load_dotenv()

ok_string = color('OK:\t', fg='green')
fail_string = color('FAIL:\t', fg='red')

oracledb_user = os.getenv("DB_USER")
oracledb_password = os.getenv("DB_PASSWORD")
oracledb_connection_string = os.getenv("CONNECTION_STRING")


def db_connectivity():
    connection = oracledb.connect(
        user=oracledb_user, password=oracledb_password, dsn=oracledb_connection_string)
    cursor = connection.cursor()
    sql = """select sysdate from dual"""

    try:
        cursor.execute(sql)
        print(f'{ok_string}DB Connectivity')
    except Exception as e:
        print(f'{fail_string}DB Connectivity: {e.args.message}')




def main():
    print("Checking setup...")
    db_connectivity()


if __name__ == '__main__':
    main()
