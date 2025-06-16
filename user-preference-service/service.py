from database import get_db_connection

def fetch_user_preferences(user_id):
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
