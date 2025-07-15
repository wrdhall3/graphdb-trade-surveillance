#!/usr/bin/env python3
"""
Simple Neo4j connection test script
"""
import os
from dotenv import load_dotenv
from neo4j import GraphDatabase
import sys

# Load environment variables
load_dotenv()

def test_neo4j_connection():
    # Get credentials from environment
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    username = os.getenv("NEO4J_USERNAME", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "password")
    
    print(f"🔍 Testing Neo4j connection...")
    print(f"   URI: {uri}")
    print(f"   Username: {username}")
    print(f"   Password: {'*' * len(password)}")
    
    try:
        # Test connection
        driver = GraphDatabase.driver(uri, auth=(username, password))
        
        with driver.session() as session:
            result = session.run("RETURN 'Hello Neo4j!' as message")
            record = result.single()
            message = record["message"]
            
        driver.close()
        
        print(f"✅ Connection successful!")
        print(f"   Response: {message}")
        
        # Test basic query
        driver = GraphDatabase.driver(uri, auth=(username, password))
        with driver.session() as session:
            result = session.run("CALL db.labels()")
            labels = [record["label"] for record in result]
            
        driver.close()
        
        print(f"📊 Database labels found: {labels}")
        return True
        
    except Exception as e:
        print(f"❌ Connection failed!")
        print(f"   Error: {e}")
        
        # Provide helpful hints
        if "authentication failure" in str(e):
            print("\n💡 Possible solutions:")
            print("   1. Check your Neo4j password")
            print("   2. Reset Neo4j password if needed")
            print("   3. Make sure .env file has correct NEO4J_PASSWORD")
            
        elif "connection refused" in str(e):
            print("\n💡 Possible solutions:")
            print("   1. Start your Neo4j database")
            print("   2. Check if Neo4j is running on port 7687")
            print("   3. Verify NEO4J_URI in .env file")
            
        return False

if __name__ == "__main__":
    success = test_neo4j_connection()
    sys.exit(0 if success else 1) 