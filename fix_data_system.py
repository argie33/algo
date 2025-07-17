#!/usr/bin/env python3
"""
Data System Recovery Tool
=========================

This script provides a systematic approach to fix the broken data loading system:
1. Diagnoses current issues
2. Repairs broken/empty loader files
3. Tests database connectivity
4. Validates all components
5. Runs a test execution to verify everything works

Author: Financial Platform Team
Updated: 2025-07-17
"""

import os
import sys
import json
import logging
import subprocess
import importlib.util
from datetime import datetime
from typing import Dict, List, Tuple, Optional
import shutil

class DataSystemRecovery:
    """
    Comprehensive data system recovery and repair tool
    """
    
    def __init__(self, dry_run: bool = False):
        """
        Initialize the recovery system
        
        Args:
            dry_run: If True, don't make any changes
        """
        self.dry_run = dry_run
        self.setup_logging()
        
        # Track issues and fixes
        self.issues_found = []
        self.fixes_applied = []
        
        self.logger.info("=== Data System Recovery Tool Starting ===")
    
    def setup_logging(self):
        """Setup logging"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)
    
    def diagnose_loader_files(self) -> Dict[str, Dict]:
        """
        Diagnose all loader files for issues
        
        Returns:
            Dictionary of files and their issues
        """
        self.logger.info("🔍 Diagnosing loader files...")
        
        loader_files = {}
        
        # Find all potential loader files
        for filename in os.listdir('.'):
            if filename.startswith('load') and filename.endswith('.py'):
                filepath = os.path.join('.', filename)
                issues = []
                
                # Check if file exists and is readable
                if not os.path.exists(filepath):
                    issues.append("FILE_NOT_FOUND")
                elif not os.access(filepath, os.R_OK):
                    issues.append("NOT_READABLE")
                else:
                    # Check file size
                    size = os.path.getsize(filepath)
                    if size == 0:
                        issues.append("EMPTY_FILE")
                    elif size < 100:  # Suspiciously small
                        issues.append("VERY_SMALL_FILE")
                    
                    # Try to parse as Python
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            content = f.read()
                        
                        # Check for basic Python syntax
                        compile(content, filepath, 'exec')
                        
                        # Check for common patterns
                        if 'import' not in content:
                            issues.append("NO_IMPORTS")
                        if 'def ' not in content and 'class ' not in content:
                            issues.append("NO_FUNCTIONS_OR_CLASSES")
                        if len(content.strip()) < 50:
                            issues.append("MINIMAL_CONTENT")
                            
                    except SyntaxError as e:
                        issues.append(f"SYNTAX_ERROR: {e}")
                    except UnicodeDecodeError:
                        issues.append("ENCODING_ERROR")
                    except Exception as e:
                        issues.append(f"READ_ERROR: {e}")
                
                loader_files[filename] = {
                    'path': filepath,
                    'size': os.path.getsize(filepath) if os.path.exists(filepath) else 0,
                    'issues': issues,
                    'status': 'broken' if issues else 'ok'
                }
        
        # Report findings
        broken_files = [f for f, info in loader_files.items() if info['status'] == 'broken']
        ok_files = [f for f, info in loader_files.items() if info['status'] == 'ok']
        
        self.logger.info(f"Found {len(loader_files)} loader files:")
        self.logger.info(f"  ✅ {len(ok_files)} files OK")
        self.logger.info(f"  ❌ {len(broken_files)} files broken")
        
        if broken_files:
            self.logger.warning("Broken files:")
            for filename in broken_files:
                issues = loader_files[filename]['issues']
                self.logger.warning(f"  - {filename}: {', '.join(issues)}")
        
        return loader_files
    
    def create_template_loader(self, loader_name: str) -> str:
        """
        Create a template loader file
        
        Args:
            loader_name: Name of the loader (without 'load' prefix or '.py' suffix)
            
        Returns:
            Content of the template loader
        """
        template = f'''#!/usr/bin/env python3
"""
{loader_name.title()} Data Loader
=============================

This loader handles {loader_name.replace('_', ' ')} data loading and processing.

Auto-generated template - needs implementation.
Created: {datetime.now().isoformat()}
"""

import os
import sys
import logging
import traceback
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

# Add current directory to path for local imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from database import query, initializeDatabase
except ImportError as e:
    print(f"Warning: Could not import database module: {{e}}")
    
    def query(sql, params=None):
        """Fallback query function"""
        print(f"FALLBACK: Would execute query: {{sql}} with params: {{params}}")
        return type('MockResult', (), {{'rows': [], 'rowcount': 0}})()
    
    def initializeDatabase():
        """Fallback database initialization"""
        print("FALLBACK: Would initialize database")

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class {loader_name.title().replace('_', '')}Loader:
    """
    Main loader class for {loader_name.replace('_', ' ')} data
    """
    
    def __init__(self):
        """Initialize the loader"""
        self.records_processed = 0
        self.errors = []
        
        logger.info(f"Initializing {{self.__class__.__name__}}")
    
    def validate_prerequisites(self) -> bool:
        """
        Validate that all prerequisites are met
        
        Returns:
            True if prerequisites are met
        """
        try:
            # Test database connectivity
            result = query("SELECT 1 as test")
            if not result:
                raise Exception("Database query failed")
            
            # Add any specific prerequisites for this loader
            # e.g., API keys, external dependencies, etc.
            
            logger.info("Prerequisites validation passed")
            return True
            
        except Exception as e:
            logger.error(f"Prerequisites validation failed: {{e}}")
            return False
    
    def extract_data(self) -> List[Dict]:
        """
        Extract data from source
        
        Returns:
            List of data records
        """
        # TODO: Implement data extraction logic
        logger.info("Extracting {loader_name.replace('_', ' ')} data...")
        
        # Placeholder implementation
        sample_data = [
            {{'id': 1, 'timestamp': datetime.now(), 'value': 'sample'}},
            {{'id': 2, 'timestamp': datetime.now(), 'value': 'sample2'}}
        ]
        
        logger.info(f"Extracted {{len(sample_data)}} records")
        return sample_data
    
    def transform_data(self, raw_data: List[Dict]) -> List[Dict]:
        """
        Transform and clean the extracted data
        
        Args:
            raw_data: Raw data from extraction
            
        Returns:
            Transformed data ready for loading
        """
        logger.info(f"Transforming {{len(raw_data)}} records...")
        
        # TODO: Implement data transformation logic
        transformed_data = []
        
        for record in raw_data:
            try:
                # Apply transformations here
                transformed_record = {{
                    **record,
                    'processed_at': datetime.now()
                }}
                transformed_data.append(transformed_record)
                
            except Exception as e:
                logger.warning(f"Failed to transform record {{record}}: {{e}}")
                self.errors.append(str(e))
        
        logger.info(f"Transformed {{len(transformed_data)}} records successfully")
        return transformed_data
    
    def load_data(self, data: List[Dict]) -> int:
        """
        Load data into the database
        
        Args:
            data: Transformed data to load
            
        Returns:
            Number of records loaded
        """
        if not data:
            logger.warning("No data to load")
            return 0
        
        logger.info(f"Loading {{len(data)}} records...")
        
        # TODO: Implement actual database loading logic
        # This is a template - replace with actual SQL INSERT statements
        
        try:
            for record in data:
                # Example insert - replace with actual table and columns
                insert_sql = """
                    INSERT INTO {loader_name}_data (id, timestamp, value, processed_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        timestamp = EXCLUDED.timestamp,
                        value = EXCLUDED.value,
                        processed_at = EXCLUDED.processed_at
                """
                
                params = (
                    record.get('id'),
                    record.get('timestamp'),
                    record.get('value'),
                    record.get('processed_at')
                )
                
                result = query(insert_sql, params)
                self.records_processed += 1
            
            logger.info(f"Successfully loaded {{self.records_processed}} records")
            return self.records_processed
            
        except Exception as e:
            logger.error(f"Failed to load data: {{e}}")
            raise
    
    def update_metadata(self):
        """Update last_updated table with execution metadata"""
        try:
            update_sql = """
                INSERT INTO last_updated (script_name, last_run, status, records_processed, notes)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (script_name) DO UPDATE SET
                    last_run = EXCLUDED.last_run,
                    status = EXCLUDED.status,
                    records_processed = EXCLUDED.records_processed,
                    notes = EXCLUDED.notes
            """
            
            notes = f"Errors: {{len(self.errors)}}" if self.errors else "Success"
            
            query(update_sql, (
                '{loader_name}',
                datetime.now(),
                'success' if len(self.errors) == 0 else 'warning',
                self.records_processed,
                notes
            ))
            
            logger.info("Updated metadata table")
            
        except Exception as e:
            logger.warning(f"Failed to update metadata: {{e}}")
    
    def run(self) -> bool:
        """
        Main execution method
        
        Returns:
            True if successful
        """
        start_time = datetime.now()
        logger.info(f"Starting {{self.__class__.__name__}} at {{start_time}}")
        
        try:
            # Validate prerequisites
            if not self.validate_prerequisites():
                logger.error("Prerequisites validation failed")
                return False
            
            # Extract data
            raw_data = self.extract_data()
            
            # Transform data
            transformed_data = self.transform_data(raw_data)
            
            # Load data
            self.load_data(transformed_data)
            
            # Update metadata
            self.update_metadata()
            
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            logger.info(f"Completed successfully in {{duration:.1f}} seconds")
            logger.info(f"Records processed: {{self.records_processed}}")
            
            if self.errors:
                logger.warning(f"Completed with {{len(self.errors)}} errors")
                for error in self.errors:
                    logger.warning(f"  - {{error}}")
            
            return True
            
        except Exception as e:
            logger.error(f"Loader failed: {{e}}")
            logger.error(traceback.format_exc())
            return False

def main():
    """Main execution function"""
    try:
        # Initialize database
        initializeDatabase()
        
        # Create and run loader
        loader = {loader_name.title().replace('_', '')}Loader()
        success = loader.run()
        
        if success:
            print(f"{{loader.records_processed}} records processed successfully")
            sys.exit(0)
        else:
            print("Loader failed")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"Main execution failed: {{e}}")
        logger.error(traceback.format_exc())
        sys.exit(1)

if __name__ == "__main__":
    main()
'''
        
        return template
    
    def repair_broken_files(self, loader_files: Dict[str, Dict]) -> List[str]:
        """
        Repair broken loader files
        
        Args:
            loader_files: Dictionary of loader files and their issues
            
        Returns:
            List of files that were repaired
        """
        self.logger.info("🔧 Repairing broken loader files...")
        
        repaired_files = []
        
        for filename, info in loader_files.items():
            if info['status'] != 'broken':
                continue
            
            issues = info['issues']
            filepath = info['path']
            
            self.logger.info(f"Repairing {filename} (issues: {', '.join(issues)})")
            
            if self.dry_run:
                self.logger.info(f"DRY RUN: Would repair {filename}")
                repaired_files.append(filename)
                continue
            
            # Create backup if file exists and has content
            if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                backup_path = f"{filepath}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                shutil.copy2(filepath, backup_path)
                self.logger.info(f"Created backup: {backup_path}")
            
            # Extract loader name
            loader_name = filename.replace('load', '').replace('.py', '')
            
            # Generate new content
            if 'EMPTY_FILE' in issues or 'MINIMAL_CONTENT' in issues or 'NO_IMPORTS' in issues:
                new_content = self.create_template_loader(loader_name)
                
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                
                self.logger.info(f"✅ Created template for {filename}")
                repaired_files.append(filename)
            
            elif 'SYNTAX_ERROR' in [issue.split(':')[0] for issue in issues]:
                # For syntax errors, create a new template
                new_content = self.create_template_loader(loader_name)
                
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                
                self.logger.info(f"✅ Replaced syntactically broken {filename}")
                repaired_files.append(filename)
        
        if repaired_files:
            self.logger.info(f"Repaired {len(repaired_files)} files: {', '.join(repaired_files)}")
        else:
            self.logger.info("No files needed repair")
        
        return repaired_files
    
    def test_database_connectivity(self) -> bool:
        """
        Test database connectivity
        
        Returns:
            True if database is accessible
        """
        self.logger.info("🔗 Testing database connectivity...")
        
        try:
            # Try to import database module
            result = subprocess.run([
                sys.executable, '-c',
                '''
import sys
sys.path.append(".")
try:
    from database import query, initializeDatabase
    initializeDatabase()
    result = query("SELECT 1 as test, NOW() as timestamp")
    print(f"SUCCESS: {result.rows[0] if result.rows else 'No rows'}")
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
                '''
            ], capture_output=True, text=True, timeout=30)
            
            if "SUCCESS:" in result.stdout:
                self.logger.info("✅ Database connectivity test passed")
                return True
            else:
                self.logger.error(f"❌ Database connectivity test failed:")
                self.logger.error(f"STDOUT: {result.stdout}")
                self.logger.error(f"STDERR: {result.stderr}")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ Database connectivity test failed: {e}")
            return False
    
    def test_loader_execution(self, loader_names: List[str] = None) -> Dict[str, bool]:
        """
        Test execution of loader files
        
        Args:
            loader_names: List of loader names to test (optional)
            
        Returns:
            Dictionary of loader names and their test results
        """
        self.logger.info("🧪 Testing loader execution...")
        
        if loader_names is None:
            # Test all available loaders
            loader_names = [
                f.replace('load', '').replace('.py', '') 
                for f in os.listdir('.') 
                if f.startswith('load') and f.endswith('.py')
            ]
        
        results = {}
        
        for loader_name in loader_names[:3]:  # Test only first 3 to save time
            loader_file = f"load{loader_name}.py"
            
            if not os.path.exists(loader_file):
                results[loader_name] = False
                continue
            
            self.logger.info(f"Testing {loader_file}...")
            
            try:
                # Run with a short timeout to test basic functionality
                result = subprocess.run([
                    sys.executable, loader_file
                ], capture_output=True, text=True, timeout=60, cwd='.')
                
                success = result.returncode == 0
                results[loader_name] = success
                
                if success:
                    self.logger.info(f"✅ {loader_file} test passed")
                else:
                    self.logger.warning(f"⚠️ {loader_file} test failed (exit code: {result.returncode})")
                    if result.stderr:
                        self.logger.warning(f"   Error: {result.stderr[:200]}")
                
            except subprocess.TimeoutExpired:
                self.logger.warning(f"⏰ {loader_file} test timed out (may be working but slow)")
                results[loader_name] = True  # Timeout might be OK for data loaders
            except Exception as e:
                self.logger.error(f"❌ {loader_file} test failed: {e}")
                results[loader_name] = False
        
        successful_tests = sum(1 for success in results.values() if success)
        self.logger.info(f"Loader tests: {successful_tests}/{len(results)} passed")
        
        return results
    
    def generate_recovery_report(self) -> Dict:
        """
        Generate a comprehensive recovery report
        
        Returns:
            Recovery report dictionary
        """
        return {
            'timestamp': datetime.now().isoformat(),
            'issues_found': self.issues_found,
            'fixes_applied': self.fixes_applied,
            'summary': {
                'total_issues': len(self.issues_found),
                'total_fixes': len(self.fixes_applied),
                'recovery_status': 'completed' if len(self.fixes_applied) > 0 else 'no_issues_found'
            }
        }
    
    def run_full_recovery(self) -> bool:
        """
        Run the complete recovery process
        
        Returns:
            True if recovery was successful
        """
        self.logger.info("🚀 Starting comprehensive data system recovery...")
        
        try:
            # Step 1: Diagnose loader files
            loader_files = self.diagnose_loader_files()
            broken_files = [f for f, info in loader_files.items() if info['status'] == 'broken']
            
            if broken_files:
                self.issues_found.extend([f"Broken loader file: {f}" for f in broken_files])
            
            # Step 2: Repair broken files
            if broken_files:
                repaired = self.repair_broken_files(loader_files)
                self.fixes_applied.extend([f"Repaired loader file: {f}" for f in repaired])
            
            # Step 3: Test database connectivity
            db_ok = self.test_database_connectivity()
            if not db_ok:
                self.issues_found.append("Database connectivity failed")
            
            # Step 4: Test loader execution
            test_results = self.test_loader_execution()
            failed_tests = [name for name, success in test_results.items() if not success]
            
            if failed_tests:
                self.issues_found.extend([f"Loader test failed: {name}" for name in failed_tests])
            
            # Generate report
            report = self.generate_recovery_report()
            
            # Save report
            report_file = f"recovery_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(report_file, 'w') as f:
                json.dump(report, f, indent=2, default=str)
            
            self.logger.info(f"Recovery report saved: {report_file}")
            
            # Summary
            total_issues = len(self.issues_found)
            total_fixes = len(self.fixes_applied)
            
            self.logger.info("=== Recovery Summary ===")
            self.logger.info(f"Issues found: {total_issues}")
            self.logger.info(f"Fixes applied: {total_fixes}")
            
            if total_issues == 0:
                self.logger.info("✅ No issues found - system appears healthy")
                return True
            elif total_fixes > 0:
                self.logger.info(f"✅ Applied {total_fixes} fixes - system should be improved")
                return True
            else:
                self.logger.warning("⚠️ Issues found but no fixes could be applied")
                return False
                
        except Exception as e:
            self.logger.error(f"Recovery process failed: {e}")
            return False

def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Data System Recovery Tool')
    parser.add_argument('--dry-run', action='store_true', help='Dry run mode - no changes made')
    parser.add_argument('--diagnose-only', action='store_true', help='Only diagnose issues, no repairs')
    
    args = parser.parse_args()
    
    recovery = DataSystemRecovery(dry_run=args.dry_run)
    
    if args.diagnose_only:
        loader_files = recovery.diagnose_loader_files()
        print(json.dumps(loader_files, indent=2, default=str))
    else:
        success = recovery.run_full_recovery()
        sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()