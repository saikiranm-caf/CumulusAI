# train.py
import tensorflow as tf
from tensorflow.keras import layers
import pandas as pd
import numpy as np
import os
from dotenv import load_dotenv
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

def main():
    try:
        # Load and validate data
        data = pd.read_csv("training_data.csv")
        logger.info(f"Loaded data with {len(data)} rows")

        # Ensure Message_Index is numeric and handle NaN
        data['Message_Index'] = pd.to_numeric(data['Message_Index'], errors='coerce')
        if data['Message_Index'].isna().any():
            logger.warning("NaN detected in Message_Index, dropping invalid rows")
            data = data.dropna(subset=['Message_Index'])
            if data.empty:
                raise ValueError("No valid data after dropping NaN values")

        # Validate range [0, 19]
        if not (data['Message_Index'].between(0, 19).all()):
            logger.error(f"Message_Index out of range [0, 19]: {data['Message_Index'].min()} to {data['Message_Index'].max()}")
            raise ValueError("Message_Index must be between 0 and 19")

        X = data[['Age', 'Gender_M', 'Gender_F', 'Near_Park', 'In_Gym', 'At_School_Zone', 'In_Shopping_Mall', 'At_Religious_Place', 'Near_Hospital', 'At_Beach_or_Lake', 'At_Library', 'At_Movie_Theatre', 'Driving', 'Female_in_Public', 'Teen_at_Home_Study', 'Child_at_Play', 'Elderly_User', 'Late_Night_Use', 'Work_Hours', 'Weekend_Chill', 'At_Outdoor_Event', 'At_Home', 'Walking_Jogging']].values
        y = data['Message_Index'].values.astype(np.int32)

    except FileNotFoundError:
        logger.error("Warning: training_data.csv not found. Please provide the data file.")
        raise
    except Exception as e:
        logger.error(f"Data loading error: {e}")
        raise

    # Define model
    model = tf.keras.Sequential([
        layers.Dense(64, activation='relu', input_shape=(X.shape[1],)),
        layers.Dense(32, activation='relu'),
        layers.Dense(20, activation='softmax')
    ])
    model.compile(optimizer='adam', loss='sparse_categorical_crossentropy', metrics=['accuracy'])

    # Train model
    logger.info("Starting model training...")
    model.fit(X, y, epochs=10, batch_size=32, validation_split=0.2)

    # Save model
    model_path = os.getenv("MODEL_PATH", "recommendation_model.h5")
    model.save(model_path)
    logger.info(f"Model saved to {model_path}")

if __name__ == "__main__":
    main()