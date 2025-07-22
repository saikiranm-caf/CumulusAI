from database import get_db_connection

def fetch_user_preferences(user_id):
    print(f"🔥Control at user-prefservice")
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    query = """
        SELECT 'system' AS defined, activity_name, activity_description
        FROM activities_info
        WHERE user_id = %s

        UNION ALL

        SELECT 'custom' AS defined, activity_name, activity_description
        FROM custom_activities_info
        WHERE user_id = %s
    """
    cursor.execute(query, (user_id, user_id))
    result = cursor.fetchall()

    cursor.close()
    conn.close()
    return result


# def fetch_user_preferences(user_id):
#     conn = get_db_connection()
#     cursor = conn.cursor(dictionary=True)

#     # Existing query for activities...

#     # Add behavior query (assume a new table 'user_behavior' with columns like 'behavior_type', 'frequency')
#     behavior_query = """
#         SELECT behavior_type, frequency
#         FROM user_behavior
#         WHERE user_id = %s
#     """
#     cursor.execute(behavior_query, (user_id,))
#     behaviors = cursor.fetchall()

#     cursor.close()
#     conn.close()
#     return {"activities": result, "behaviors": behaviors}
