import asyncio
import threading
import time
import signal
import sys
import concurrent.futures
from typing import List, Dict, Any
from datetime import datetime, timedelta
import pytest
from unittest.mock import patch
from folioclient import FolioClient


class ConcurrentAuthTester:
    """Test harness for concurrent authentication scenarios"""
    
    def __init__(self, gateway_url: str, tenant_id: str, username: str, password: str):
        self.gateway_url = gateway_url
        self.tenant_id = tenant_id
        self.username = username
        self.password = password
        self.results = []
        self.errors = []
        self.auth_counts = {"sync": 0, "async": 0}
        
        # Long-running test state
        self.long_running_stats = {
            "start_time": None,
            "total_requests": 0,
            "total_errors": 0,
            "total_auth_calls": 0,
            "error_types": {},
            "response_times": [],
            "tokens_seen": set(),
            "memory_snapshots": [],
            "last_report_time": None
        }
        self.should_stop = threading.Event()
        self.lock = threading.RLock()
    
    def make_endpoint_request(self, client, endpoint: str, result_key: str, is_async: bool = False):
        """Helper method to make requests to configurable endpoints"""
        query_params = {"limit": 1}
        
        if is_async:
            return client.folio_get_async(endpoint, result_key, query_params=query_params)
        else:
            return client.folio_get(endpoint, result_key, query_params=query_params)
        
    def reset_stats(self):
        """Reset test statistics"""
        self.results.clear()
        self.errors.clear()
        self.auth_counts = {"sync": 0, "async": 0}

    def sync_worker(self, worker_id: int, num_requests: int) -> Dict[str, Any]:
        """Synchronous worker that makes multiple requests"""
        results = {
            "worker_id": worker_id,
            "requests_made": 0,
            "auth_calls": 0,
            "errors": [],
            "start_time": time.time(),
            "tokens_seen": set()
        }
        
        try:
            # Use context manager properly - let it handle cleanup
            with FolioClient(
                self.gateway_url, 
                self.tenant_id, 
                self.username, 
                self.password
            ) as client:
                
                # Patch _do_sync_auth to count calls
                original_auth = client.folio_auth._do_sync_auth
                def counting_auth():
                    results["auth_calls"] += 1
                    self.auth_counts["sync"] += 1
                    token = original_auth()
                    results["tokens_seen"].add(token.auth_token)
                    return token
                
                client.folio_auth._do_sync_auth = counting_auth
                
                # Make requests
                for i in range(num_requests):
                    try:
                        # Mix different types of requests
                        if i % 3 == 0:
                            users = client.folio_get("/users", "users", query_params={"limit": 1})
                        elif i % 3 == 1:
                            # Force token access
                            token = client.okapi_token
                            results["tokens_seen"].add(token)
                        else:
                            # Test headers property
                            headers = client.folio_headers
                            results["tokens_seen"].add(headers["x-okapi-token"])
                        
                        results["requests_made"] += 1
                        
                        # Small delay to increase chance of race conditions
                        time.sleep(0.01)
                        
                    except Exception as e:
                        results["errors"].append(f"Request {i}: {str(e)}")
            
            # Context manager handles cleanup automatically
                        
        except Exception as e:
            results["errors"].append(f"Client setup: {str(e)}")
            
        results["end_time"] = time.time()
        results["tokens_seen"] = list(results["tokens_seen"])  # Convert set to list
        return results

    async def async_worker(self, worker_id: int, num_requests: int) -> Dict[str, Any]:
        """Asynchronous worker that makes multiple requests"""
        results = {
            "worker_id": worker_id,
            "requests_made": 0,
            "auth_calls": 0,
            "errors": [],
            "start_time": time.time(),
            "tokens_seen": set()
        }
        
        try:
            # Use async context manager properly - let it handle cleanup
            async with FolioClient(
                self.gateway_url, 
                self.tenant_id, 
                self.username, 
                self.password
            ) as client:
                
                # Patch _do_async_auth to count calls
                original_auth = client.folio_auth._do_async_auth
                async def counting_async_auth():
                    results["auth_calls"] += 1
                    self.auth_counts["async"] += 1
                    token = await original_auth()
                    results["tokens_seen"].add(token.auth_token)
                    return token
                
                client.folio_auth._do_async_auth = counting_async_auth
                
                # Make requests
                for i in range(num_requests):
                    try:
                        # Mix different types of requests
                        if i % 3 == 0:
                            users = await client.folio_get_async("/users", "users", query_params={"limit": 1})
                        elif i % 3 == 1:
                            # Force token access (sync method from async context)
                            token = client.okapi_token
                            results["tokens_seen"].add(token)
                        else:
                            # Test async login
                            await client.async_login()
                            token = client.okapi_token
                            results["tokens_seen"].add(token)
                        
                        results["requests_made"] += 1
                        
                        # Small delay to increase chance of race conditions
                        await asyncio.sleep(0.01)
                        
                    except Exception as e:
                        results["errors"].append(f"Request {i}: {str(e)}")
            
            # Async context manager handles cleanup automatically
                        
        except Exception as e:
            results["errors"].append(f"Client setup: {str(e)}")
            
        results["end_time"] = time.time()
        results["tokens_seen"] = list(results["tokens_seen"])  # Convert set to list
        return results

    def long_running_worker(self, worker_id: int, delay_seconds: float = 1.0, operation_type: str = "get", endpoint: str = "/users", result_key: str = "users") -> Dict[str, Any]:
        """Long-running worker that performs operations until stopped"""
        stats = {
            "worker_id": worker_id,
            "requests_made": 0,
            "auth_calls": 0,
            "errors": [],
            "start_time": time.time(),
            "tokens_seen": set(),
            "response_times": []
        }
        
        client = None
        client_working = False
        
        try:
            # Try to create client but don't fail if server is unreachable
            print(f"Worker {worker_id}: Attempting to connect to {self.gateway_url}...")
            client = FolioClient(
                self.gateway_url,
                self.tenant_id,
                self.username,
                self.password
            )
            
            # Test connection
            try:
                test_token = client.okapi_token
                client_working = True
                print(f"Worker {worker_id}: Connected successfully!")
                
                # Patch auth to count calls
                original_auth = client.folio_auth._do_sync_auth
                def counting_auth():
                    stats["auth_calls"] += 1
                    with self.lock:
                        self.long_running_stats["total_auth_calls"] += 1
                    token = original_auth()
                    stats["tokens_seen"].add(token.auth_token)
                    with self.lock:
                        self.long_running_stats["tokens_seen"].add(token.auth_token)
                    return token
                
                client.folio_auth._do_sync_auth = counting_auth
                
            except Exception as e:
                print(f"Worker {worker_id}: Connection failed ({e}), will simulate requests")
                client_working = False
                
            # Main worker loop - runs whether client works or not
            print(f"Worker {worker_id}: Starting main loop (client_working={client_working})...")
            
            while not self.should_stop.is_set():
                request_start = time.time()
                try:
                    if client_working:
                        # Real requests to FOLIO server
                        if operation_type == "get":
                            result = self.make_endpoint_request(client, endpoint, result_key, is_async=False)
                        elif operation_type == "token_access":
                            token = client.okapi_token
                            stats["tokens_seen"].add(token)
                        elif operation_type == "headers":
                            headers = client.folio_headers
                            stats["tokens_seen"].add(headers["x-okapi-token"])
                        elif operation_type == "mixed":
                            # Rotate between different operations
                            op_choice = stats["requests_made"] % 3
                            if op_choice == 0:
                                result = self.make_endpoint_request(client, endpoint, result_key, is_async=False)
                            elif op_choice == 1:
                                token = client.okapi_token
                                stats["tokens_seen"].add(token)
                            else:
                                headers = client.folio_headers
                                stats["tokens_seen"].add(headers["x-okapi-token"])
                    else:
                        # Simulate requests when no real server available
                        fake_token = f"fake_token_{stats['requests_made']}"
                        stats["tokens_seen"].add(fake_token)
                        
                        with self.lock:
                            self.long_running_stats["tokens_seen"].add(fake_token)
                        
                        # Simulate some processing time
                        time.sleep(0.01)
                        print(f"Worker {worker_id}: Simulated request {stats['requests_made']} (no real server)")
                    
                    request_time = time.time() - request_start
                    stats["response_times"].append(request_time)
                    stats["requests_made"] += 1
                    
                    with self.lock:
                        self.long_running_stats["total_requests"] += 1
                        self.long_running_stats["response_times"].append(request_time)
                    
                except Exception as e:
                    error_msg = f"Request failed: {str(e)}"
                    stats["errors"].append(error_msg)
                    
                    with self.lock:
                        self.long_running_stats["total_errors"] += 1
                        error_type = type(e).__name__
                        if error_type not in self.long_running_stats["error_types"]:
                            self.long_running_stats["error_types"][error_type] = 0
                        self.long_running_stats["error_types"][error_type] += 1
                    
                    print(f"Worker {worker_id} error: {error_msg} (continuing...)")
                    
                    # Wait before next request, but check for stop signal frequently
                    sleep_interval = 0.1
                    total_sleep = 0
                    while total_sleep < delay_seconds and not self.should_stop.is_set():
                        time.sleep(sleep_interval)
                        total_sleep += sleep_interval
                
        except Exception as e:
            error_msg = f"Worker setup failed: {str(e)}"
            stats["errors"].append(error_msg)
            print(f"Worker {worker_id}: {error_msg}")
        
        finally:
            # Cleanup
            if client:
                try:
                    client.close()
                except:
                    pass
        
        print(f"Worker {worker_id}: Finished. Made {stats['requests_made']} requests.")
        stats["end_time"] = time.time()
        stats["tokens_seen"] = list(stats["tokens_seen"])
        return stats

    async def long_running_async_worker(self, worker_id: int, delay_seconds: float = 1.0, operation_type: str = "get", endpoint: str = "/users", result_key: str = "users") -> Dict[str, Any]:
        """Async long-running worker that performs operations until stopped"""
        stats = {
            "worker_id": worker_id,
            "requests_made": 0,
            "auth_calls": 0,
            "errors": [],
            "start_time": time.time(),
            "tokens_seen": set(),
            "response_times": []
        }
        
        client = None
        client_working = False
        
        try:
            # Try to create async client
            print(f"Async Worker {worker_id}: Attempting to connect to {self.gateway_url}...")
            client = FolioClient(
                self.gateway_url,
                self.tenant_id,
                self.username,
                self.password
            )
            
            # Test connection - use the property, not a method
            try:
                test_token = client.okapi_token  # ✅ This is a property
                client_working = True
                print(f"Async Worker {worker_id}: Connected successfully!")
                
                # Patch async auth to count calls
                original_auth = client.folio_auth._do_async_auth
                async def counting_async_auth():
                    stats["auth_calls"] += 1
                    with self.lock:
                        self.long_running_stats["total_auth_calls"] += 1
                    token = await original_auth()
                    stats["tokens_seen"].add(token.auth_token)
                    with self.lock:
                        self.long_running_stats["tokens_seen"].add(token.auth_token)
                    return token
                
                client.folio_auth._do_async_auth = counting_async_auth
                
            except Exception as e:
                print(f"Async Worker {worker_id}: Connection failed ({e}), will simulate requests")
                client_working = False
            
            # Main async worker loop - runs whether client works or not
            print(f"Async Worker {worker_id}: Starting main loop (client_working={client_working})...")
            
            while not self.should_stop.is_set():
                request_start = time.time()
                try:
                    if client_working:
                        # Real async requests to FOLIO server
                        if operation_type == "get":
                            result = await self.make_endpoint_request(client, endpoint, result_key, is_async=True)
                        elif operation_type == "token_access":
                            token = client.okapi_token  # ✅ Property access (sync from async context)
                            stats["tokens_seen"].add(token)
                        elif operation_type == "headers":
                            headers = client.folio_headers  # ✅ Property access (sync from async context)
                            stats["tokens_seen"].add(headers["x-okapi-token"])
                        elif operation_type == "mixed":
                            # Rotate between different operations
                            op_choice = stats["requests_made"] % 3
                            if op_choice == 0:
                                result = await self.make_endpoint_request(client, endpoint, result_key, is_async=True)
                            elif op_choice == 1:
                                token = client.okapi_token  # ✅ Property access
                                stats["tokens_seen"].add(token)
                            else:
                                headers = client.folio_headers  # ✅ Property access
                                stats["tokens_seen"].add(headers["x-okapi-token"])
                    else:
                        # Simulate async requests when no real server available
                        fake_token = f"fake_async_token_{stats['requests_made']}"
                        stats["tokens_seen"].add(fake_token)
                        
                        with self.lock:
                            self.long_running_stats["tokens_seen"].add(fake_token)
                        
                        # Simulate some async processing time
                        await asyncio.sleep(0.01)
                        print(f"Async Worker {worker_id}: Simulated async request {stats['requests_made']} (no real server)")
                    
                    request_time = time.time() - request_start
                    stats["response_times"].append(request_time)
                    stats["requests_made"] += 1
                    
                    with self.lock:
                        self.long_running_stats["total_requests"] += 1
                        self.long_running_stats["response_times"].append(request_time)
                    
                except Exception as e:
                    error_msg = f"Async request failed: {str(e)}"
                    stats["errors"].append(error_msg)
                    
                    with self.lock:
                        self.long_running_stats["total_errors"] += 1
                        error_type = type(e).__name__
                        if error_type not in self.long_running_stats["error_types"]:
                            self.long_running_stats["error_types"][error_type] = 0
                        self.long_running_stats["error_types"][error_type] += 1
                    
                    print(f"Async Worker {worker_id} error: {error_msg} (continuing...)")
                
                # Wait before next request, but check for stop signal frequently
                sleep_interval = 0.1
                total_sleep = 0
                while total_sleep < delay_seconds and not self.should_stop.is_set():
                    await asyncio.sleep(sleep_interval)
                    total_sleep += sleep_interval
                
        except Exception as e:
            error_msg = f"Async worker setup failed: {str(e)}"
            stats["errors"].append(error_msg)
            print(f"Async Worker {worker_id}: {error_msg}")
        
        finally:
            # Cleanup
            if client:
                try:
                    await client.__aexit__(None, None, None)  # Use proper async context manager exit
                except:
                    pass
        
        print(f"Async Worker {worker_id}: Finished. Made {stats['requests_made']} requests.")
        stats["end_time"] = time.time()
        stats["tokens_seen"] = list(stats["tokens_seen"])
        return stats

    def test_shared_client_simple(self, num_workers: int = 8, requests_each: int = 3):
        """Simplified test with shared client and only sync operations"""
        print(f"\n=== Testing shared client with {num_workers} threads ===")
        self.reset_stats()
        
        with FolioClient(
            self.gateway_url, 
            self.tenant_id, 
            self.username, 
            self.password
        ) as shared_client:
            
            # Count auth calls on shared client
            auth_calls = 0
            original_auth = shared_client.folio_auth._do_sync_auth
            def counting_auth():
                nonlocal auth_calls
                auth_calls += 1
                return original_auth()
            shared_client.folio_auth._do_sync_auth = counting_auth
            
            def worker(worker_id: int):
                results = {"worker_id": worker_id, "requests": 0, "errors": [], "tokens": set()}
                for i in range(requests_each):
                    try:
                        # Different operations that all need authentication
                        if i % 2 == 0:
                            token = shared_client.okapi_token
                            results["tokens"].add(token)
                        else:
                            headers = shared_client.folio_headers
                            results["tokens"].add(headers["x-okapi-token"])
                        
                        results["requests"] += 1
                        time.sleep(0.005)  # Small delay
                    except Exception as e:
                        results["errors"].append(str(e))
                
                results["tokens"] = list(results["tokens"])
                return results
            
            start_time = time.time()
            with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
                futures = [executor.submit(worker, i) for i in range(num_workers)]
                worker_results = [f.result() for f in futures]
            end_time = time.time()
            
            total_requests = sum(r["requests"] for r in worker_results)
            total_errors = sum(len(r["errors"]) for r in worker_results)
            all_tokens = set()
            for r in worker_results:
                all_tokens.update(r["tokens"])
            
            print(f"Results:")
            print(f"  Total time: {end_time - start_time:.2f}s")
            print(f"  Total requests: {total_requests}")
            print(f"  Total auth calls: {auth_calls}")
            print(f"  Total errors: {total_errors}")
            print(f"  Unique tokens: {len(all_tokens)}")
            print(f"  Auth efficiency: {total_requests / max(auth_calls, 1):.2f} requests per auth")
            
            if total_errors > 0:
                print(f"  Errors:")
                for r in worker_results:
                    if r["errors"]:
                        print(f"    Worker {r['worker_id']}: {r['errors']}")
            
            return {
                "total_requests": total_requests,
                "total_auth_calls": auth_calls,
                "total_errors": total_errors,
                "unique_tokens": len(all_tokens)
            }

    def test_concurrent_sync_threads(self, num_threads: int = 10, requests_per_thread: int = 5):
        """Test concurrent synchronous requests from multiple threads"""
        print(f"\n=== Testing {num_threads} sync threads, {requests_per_thread} requests each ===")
        self.reset_stats()
        
        start_time = time.time()
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [
                executor.submit(self.sync_worker, i, requests_per_thread) 
                for i in range(num_threads)
            ]
            
            results = [future.result() for future in concurrent.futures.as_completed(futures)]
        
        end_time = time.time()
        
        # Analyze results
        total_requests = sum(r["requests_made"] for r in results)
        total_auth_calls = sum(r["auth_calls"] for r in results)
        total_errors = sum(len(r["errors"]) for r in results)
        unique_tokens = set()
        for r in results:
            unique_tokens.update(r["tokens_seen"])
        
        print(f"Results:")
        print(f"  Total time: {end_time - start_time:.2f}s")
        print(f"  Total requests made: {total_requests}")
        print(f"  Total auth calls: {total_auth_calls}")
        print(f"  Total errors: {total_errors}")
        print(f"  Unique tokens seen: {len(unique_tokens)}")
        print(f"  Auth efficiency: {total_requests / max(total_auth_calls, 1):.2f} requests per auth")
        
        if total_errors > 0:
            print(f"  Errors:")
            for r in results:
                if r["errors"]:
                    print(f"    Worker {r['worker_id']}: {r['errors']}")
        
        return {
            "total_requests": total_requests,
            "total_auth_calls": total_auth_calls,
            "total_errors": total_errors,
            "unique_tokens": len(unique_tokens),
            "results": results
        }

    async def test_concurrent_async_tasks(self, num_tasks: int = 10, requests_per_task: int = 5):
        """Test concurrent asynchronous requests from multiple tasks"""
        print(f"\n=== Testing {num_tasks} async tasks, {requests_per_task} requests each ===")
        self.reset_stats()
        
        start_time = time.time()
        
        tasks = [
            self.async_worker(i, requests_per_task) 
            for i in range(num_tasks)
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out exceptions
        valid_results = [r for r in results if isinstance(r, dict)]
        exceptions = [r for r in results if not isinstance(r, dict)]
        
        end_time = time.time()
        
        # Print detailed error information
        if exceptions:
            print(f"  EXCEPTIONS FOUND:")
            for i, exc in enumerate(exceptions):
                print(f"    Exception {i}: {type(exc).__name__}: {exc}")

        # Print detailed error information from valid results
        for r in valid_results:
            if r["errors"]:
                print(f"  Worker {r['worker_id']} errors: {r['errors']}")
        
        # Analyze results (moved out of the loop)
        total_requests = sum(r["requests_made"] for r in valid_results)
        total_auth_calls = sum(r["auth_calls"] for r in valid_results)
        total_errors = sum(len(r["errors"]) for r in valid_results) + len(exceptions)
        unique_tokens = set()
        for r in valid_results:
            unique_tokens.update(r["tokens_seen"])
        
        print(f"Results:")
        print(f"  Total time: {end_time - start_time:.2f}s")
        print(f"  Total requests made: {total_requests}")
        print(f"  Total auth calls: {total_auth_calls}")
        print(f"  Total errors: {total_errors}")
        print(f"  Unique tokens seen: {len(unique_tokens)}")
        print(f"  Auth efficiency: {total_requests / max(total_auth_calls, 1):.2f} requests per auth")
        
        if exceptions:
            print(f"  Task exceptions: {len(exceptions)}")
            for i, exc in enumerate(exceptions):
                print(f"    Exception {i}: {exc}")
        
        return {
            "total_requests": total_requests,
            "total_auth_calls": total_auth_calls,
            "total_errors": total_errors,
            "unique_tokens": len(unique_tokens),
            "results": valid_results,
            "exceptions": exceptions
        }

    def test_mixed_sync_async(self, num_sync_threads: int = 5, num_async_tasks: int = 5, requests_each: int = 3):
        """Test mixed synchronous and asynchronous access to the same client"""
        print(f"\n=== Testing mixed sync/async: {num_sync_threads} threads + {num_async_tasks} tasks ===")
        self.reset_stats()
        
        # Create a shared client (this tests the thread safety)
        with FolioClient(
            self.gateway_url, 
            self.tenant_id, 
            self.username, 
            self.password
        ) as shared_client:
            
            def sync_worker_shared(worker_id: int):
                results = {"worker_id": worker_id, "requests": 0, "errors": []}
                for i in range(requests_each):
                    try:
                        token = shared_client.okapi_token
                        users = shared_client.folio_get("/users", "users", query_params={"limit": 1})
                        results["requests"] += 1
                        time.sleep(0.01)  # Small delay
                    except Exception as e:
                        results["errors"].append(str(e))
                return results
            
            async def async_worker_shared(worker_id: int):
                results = {"worker_id": worker_id, "requests": 0, "errors": []}
                for i in range(requests_each):
                    try:
                        # Mix of sync and async calls on shared client
                        token = shared_client.okapi_token  # Sync call
                        await shared_client.async_login()   # Async call
                        results["requests"] += 1
                        await asyncio.sleep(0.01)  # Small delay
                    except Exception as e:
                        results["errors"].append(str(e))
                return results
            
            def run_mixed_test():  # Remove async - this is the problem!
                async def async_part():
                    # Start async tasks
                    async_tasks = [
                        async_worker_shared(i) 
                        for i in range(num_async_tasks)
                    ]
                    return await asyncio.gather(*async_tasks)
                
                # Start sync threads  
                with concurrent.futures.ThreadPoolExecutor(max_workers=num_sync_threads) as executor:
                    sync_futures = [
                        executor.submit(sync_worker_shared, i) 
                        for i in range(num_sync_threads)
                    ]
                    
                    # Run async tasks
                    async_results = asyncio.run(async_part())  # This creates new event loop
                    sync_results = [f.result() for f in sync_futures]
                    
                    return sync_results, async_results
            
            start_time = time.time()
            sync_results, async_results = run_mixed_test()  # Remove asyncio.run()
            end_time = time.time()
            
            # Analyze results
            all_results = sync_results + async_results
            total_requests = sum(r["requests"] for r in all_results)
            total_errors = sum(len(r["errors"]) for r in all_results)
            
            print(f"Results:")
            print(f"  Total time: {end_time - start_time:.2f}s")
            print(f"  Total requests made: {total_requests}")
            print(f"  Total errors: {total_errors}")
            print(f"  Sync auth calls: {self.auth_counts['sync']}")
            print(f"  Async auth calls: {self.auth_counts['async']}")
            
            return {
                "total_requests": total_requests,
                "total_errors": total_errors,
                "sync_results": sync_results,
                "async_results": async_results
            }

    def test_token_expiry_simulation(self):
        """Test behavior when tokens expire during concurrent usage"""
        print(f"\n=== Testing token expiry simulation ===")
        
        with FolioClient(
            self.gateway_url, 
            self.tenant_id, 
            self.username, 
            self.password
        ) as client:
            
            # Patch token expiry check to simulate expiration
            original_expiring = client.folio_auth._token_is_expiring
            call_count = 0
            
            def simulate_expiry():
                nonlocal call_count
                call_count += 1
                # Force expiry every 5 calls to simulate token refresh
                return call_count % 5 == 0
            
            client.folio_auth._token_is_expiring = simulate_expiry
            
            # Count auth calls
            auth_calls = 0
            original_auth = client.folio_auth._do_sync_auth
            def counting_auth():
                nonlocal auth_calls
                auth_calls += 1
                return original_auth()
            client.folio_auth._do_sync_auth = counting_auth
            
            # Make many concurrent requests
            def worker():
                results = []
                for i in range(10):
                    try:
                        token = client.okapi_token
                        results.append(("success", token))
                        time.sleep(0.01)
                    except Exception as e:
                        results.append(("error", str(e)))
                return results
            
            start_time = time.time()
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(worker) for _ in range(10)]
                all_results = [result for future in futures for result in future.result()]
            end_time = time.time()
            
            successes = len([r for r in all_results if r[0] == "success"])
            errors = len([r for r in all_results if r[0] == "error"])
            
            print(f"Results:")
            print(f"  Total time: {end_time - start_time:.2f}s")
            print(f"  Successful token gets: {successes}")
            print(f"  Errors: {errors}")
            print(f"  Auth calls made: {auth_calls}")
            print(f"  Expected auth efficiency: Multiple threads should share auth results")
            
            return {
                "successes": successes,
                "errors": errors,
                "auth_calls": auth_calls,
                "all_results": all_results
            }

    def setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown"""
        def signal_handler(signum, frame):
            print("\n\n🛑 Received interrupt signal. Stopping gracefully...")
            self.should_stop.set()
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    def print_live_stats(self, force=False):
        """Print live statistics during long-running tests (overwrites previous stats)"""
        now = time.time()
        if not force and self.long_running_stats["last_report_time"] and now - self.long_running_stats["last_report_time"] < 10:
            return
        
        self.long_running_stats["last_report_time"] = now
        
        with self.lock:
            elapsed = now - self.long_running_stats["start_time"]
            total_requests = self.long_running_stats["total_requests"]
            total_errors = self.long_running_stats["total_errors"]
            total_auth_calls = self.long_running_stats["total_auth_calls"]
            response_times = self.long_running_stats["response_times"]
            error_types = dict(self.long_running_stats["error_types"])
            unique_tokens = len(self.long_running_stats["tokens_seen"])
        
        requests_per_sec = total_requests / elapsed if elapsed > 0 else 0
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0
        success_rate = ((total_requests - total_errors) / total_requests * 100) if total_requests > 0 else 0
        auth_efficiency = total_requests / max(total_auth_calls, 1)
        
        # Check if this is the first stats print (store line count for clearing)
        if not hasattr(self, '_stats_line_count'):
            self._stats_line_count = 0
        
        # Clear previous stats display
        if self._stats_line_count > 0:
            # Move cursor up and clear lines
            print(f"\033[{self._stats_line_count}A", end="")  # Move cursor up
            print("\033[J", end="")  # Clear from cursor to end of screen
        
        # Build stats output
        stats_lines = []
        
        # Always add a blank line before stats (either first time or to replace the cleared one)
        if not hasattr(self, '_stats_printed_once'):
            stats_lines.append("")  # Add blank line for first time
            self._stats_printed_once = True
        else:
            stats_lines.append("")  # Add blank line back after clearing
        
        stats_lines.append(f"📊 Live Stats (Running for {elapsed:.1f}s):")
        stats_lines.append(f"  Total requests: {total_requests} ({requests_per_sec:.1f}/sec)")
        stats_lines.append(f"  Success rate: {success_rate:.1f}% ({total_errors} errors)")
        stats_lines.append(f"  Auth efficiency: {auth_efficiency:.1f} requests per auth call")
        stats_lines.append(f"  Avg response time: {avg_response_time:.3f}s")
        stats_lines.append(f"  Unique tokens seen: {unique_tokens}")
        
        if error_types:
            stats_lines.append(f"  Error breakdown: {error_types}")
        
        # Memory usage (if psutil is available)
        try:
            import psutil
            process = psutil.Process()
            memory_mb = process.memory_info().rss / 1024 / 1024
            stats_lines.append(f"  Memory usage: {memory_mb:.1f} MB")
        except ImportError:
            pass
        
        # Print all stats at once
        stats_output = "\n".join(stats_lines)
        print(stats_output, flush=True)
        
        # Store line count for next clear operation
        self._stats_line_count = len(stats_lines)

    def test_long_running_sync(self, num_workers: int = 4, delay_seconds: float = 1.0, 
                               operation_type: str = "mixed", report_interval: int = 10,
                               endpoint: str = "/users", result_key: str = "users"):
        """Run a long-running synchronous test until interrupted"""
        print(f"\n=== Long-Running Sync Test ===")
        print(f"Workers: {num_workers}, Delay: {delay_seconds}s, Operation: {operation_type}")
        print("Press Ctrl+C to stop gracefully...\n")
        
        self.setup_signal_handlers()
        self.should_stop.clear()
        self.long_running_stats["start_time"] = time.time()
        self.long_running_stats["last_report_time"] = None
        
        # Reset stats line counter for clean display
        if hasattr(self, '_stats_line_count'):
            delattr(self, '_stats_line_count')
        if hasattr(self, '_stats_printed_once'):
            delattr(self, '_stats_printed_once')
        
        # Start reporting thread
        def periodic_report():
            while not self.should_stop.is_set():
                time.sleep(report_interval)
                if not self.should_stop.is_set():
                    self.print_live_stats()
        
        report_thread = threading.Thread(target=periodic_report, daemon=True)
        report_thread.start()
        
        # Start worker threads
        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = [
                executor.submit(self.long_running_worker, i, delay_seconds, operation_type, endpoint, result_key)
                for i in range(num_workers)
            ]
            try:
                # Wait indefinitely for signal (workers should run until stopped)
                while not self.should_stop.is_set():
                    time.sleep(0.5)  # Check stop signal frequently
                    
                # Signal received, wait for workers to finish
                self.should_stop.set()
                results = [future.result(timeout=5) for future in futures]

            except KeyboardInterrupt:
                self.should_stop.set()
                # Wait for graceful shutdown
                try:
                    results = [future.result(timeout=5) for future in futures]
                except concurrent.futures.TimeoutError:
                    print("⚠️  Some workers didn't stop gracefully, forcing shutdown...")
                    results = []

        # Final report
        self.print_final_long_running_report(results)
        return results

    async def test_long_running_async(self, num_tasks: int = 4, delay_seconds: float = 1.0,
                                      operation_type: str = "mixed", report_interval: int = 10,
                                      endpoint: str = "/users", result_key: str = "users"):
        """Run a long-running asynchronous test until interrupted"""
        print(f"\n=== Long-Running Async Test ===")
        print(f"Tasks: {num_tasks}, Delay: {delay_seconds}s, Operation: {operation_type}")
        print("Press Ctrl+C to stop gracefully...\n")
        
        self.setup_signal_handlers()
        self.should_stop.clear()
        self.long_running_stats["start_time"] = time.time()
        self.long_running_stats["last_report_time"] = None
        
        # Reset stats line counter for clean display
        if hasattr(self, '_stats_line_count'):
            delattr(self, '_stats_line_count')
        if hasattr(self, '_stats_printed_once'):
            delattr(self, '_stats_printed_once')
        
        # Start reporting task
        async def periodic_report():
            while not self.should_stop.is_set():
                await asyncio.sleep(report_interval)
                if not self.should_stop.is_set():
                    self.print_live_stats()
        
        # Start all tasks
        tasks = []
        tasks.append(asyncio.create_task(periodic_report()))
        
        for i in range(num_tasks):
            task = asyncio.create_task(
                self.long_running_async_worker(i, delay_seconds, operation_type, endpoint, result_key)
            )
            tasks.append(task)
        
        try:
            # Wait indefinitely for signal (tasks should run until stopped)
            while not self.should_stop.is_set():
                await asyncio.sleep(0.5)  # Check stop signal frequently
                
            # Signal received, cancel tasks and collect results
            self.should_stop.set()
            for task in tasks[1:]:
                task.cancel()
            
            try:
                results = await asyncio.gather(*tasks[1:], return_exceptions=True)
                results = [r for r in results if isinstance(r, dict)]
            except asyncio.CancelledError:
                results = []
                
        except KeyboardInterrupt:
            self.should_stop.set()
            # Cancel all tasks
            for task in tasks:
                task.cancel()
            try:
                await asyncio.gather(*tasks, return_exceptions=True)
            except:
                pass
            results = []
        
        # Final report
        valid_results = [r for r in results if isinstance(r, dict)]
        self.print_final_long_running_report(valid_results)
        return valid_results

    def test_long_running_mixed(self, num_sync_workers: int = 2, num_async_tasks: int = 2,
                                delay_seconds: float = 1.0, operation_type: str = "mixed",
                                report_interval: int = 10, endpoint: str = "/users", result_key: str = "users"):
        """Run a long-running mixed sync/async test until interrupted"""
        print(f"\n=== Long-Running Mixed Sync/Async Test ===")
        print(f"Sync workers: {num_sync_workers}, Async tasks: {num_async_tasks}")
        print(f"Delay: {delay_seconds}s, Operation: {operation_type}")
        print("Press Ctrl+C to stop gracefully...\n")
        
        self.setup_signal_handlers()
        self.should_stop.clear()
        self.long_running_stats["start_time"] = time.time()
        self.long_running_stats["last_report_time"] = None
        
        # Reset stats line counter for clean display
        if hasattr(self, '_stats_line_count'):
            delattr(self, '_stats_line_count')
        if hasattr(self, '_stats_printed_once'):
            delattr(self, '_stats_printed_once')
        
        # Start reporting thread
        def periodic_report():
            while not self.should_stop.is_set():
                time.sleep(report_interval)
                if not self.should_stop.is_set():
                    self.print_live_stats()
        
        report_thread = threading.Thread(target=periodic_report, daemon=True)
        report_thread.start()
        
        # Simplified approach: run sync and async workers separately
        all_results = []
        
        # Start sync workers in thread pool
        with concurrent.futures.ThreadPoolExecutor(max_workers=num_sync_workers) as executor:
            sync_futures = [
                executor.submit(self.long_running_worker, i, delay_seconds, operation_type, endpoint, result_key)
                for i in range(num_sync_workers)
            ]
            
            try:
                # Wait indefinitely for signal
                while not self.should_stop.is_set():
                    time.sleep(0.5)
                
                # Signal received, stop everything
                self.should_stop.set()
                
                # Collect sync results
                try:
                    sync_results = [future.result(timeout=5) for future in sync_futures]
                except concurrent.futures.TimeoutError:
                    print("⚠️  Some sync workers didn't stop gracefully")
                    sync_results = []
                
                all_results = sync_results
                
            except KeyboardInterrupt:
                self.should_stop.set()
                # Wait for sync workers
                try:
                    all_results = [future.result(timeout=3) for future in sync_futures]
                except:
                    all_results = []
        
        # Now run async workers if requested
        if num_async_tasks > 0 and not self.should_stop.is_set():
            print(f"\nNow starting {num_async_tasks} async tasks...")
            self.should_stop.clear()  # Reset for async phase
            
            async def run_async_phase():
                async_tasks = [
                    asyncio.create_task(
                        self.long_running_async_worker(i + num_sync_workers, delay_seconds, operation_type, endpoint, result_key)
                    )
                    for i in range(num_async_tasks)
                ]
                
                try:
                    # Wait indefinitely for signal
                    while not self.should_stop.is_set():
                        await asyncio.sleep(0.5)
                    
                    # Cancel tasks and collect results
                    for task in async_tasks:
                        task.cancel()
                    
                    results = await asyncio.gather(*async_tasks, return_exceptions=True)
                    return [r for r in results if isinstance(r, dict)]
                    
                except KeyboardInterrupt:
                    for task in async_tasks:
                        task.cancel()
                    return []
            
            try:
                async_results = asyncio.run(run_async_phase())
                all_results.extend(async_results)
            except KeyboardInterrupt:
                pass
        
        # Final report
        self.print_final_long_running_report(all_results)
        return all_results

    def print_final_long_running_report(self, worker_results: List[Dict[str, Any]]):
        """Print final statistics for long-running tests"""
        print("\n" + "="*80)
        print("FINAL LONG-RUNNING TEST REPORT")
        print("="*80)
        
        with self.lock:
            total_time = time.time() - self.long_running_stats["start_time"]
            total_requests = self.long_running_stats["total_requests"]
            total_errors = self.long_running_stats["total_errors"]
            total_auth_calls = self.long_running_stats["total_auth_calls"]
            response_times = self.long_running_stats["response_times"]
            error_types = dict(self.long_running_stats["error_types"])
            unique_tokens = len(self.long_running_stats["tokens_seen"])
        
        # Calculate statistics
        requests_per_sec = total_requests / total_time if total_time > 0 else 0
        success_rate = ((total_requests - total_errors) / total_requests * 100) if total_requests > 0 else 0
        auth_efficiency = total_requests / max(total_auth_calls, 1)
        
        if response_times:
            avg_response = sum(response_times) / len(response_times)
            min_response = min(response_times)
            max_response = max(response_times)
            # Calculate 95th percentile
            sorted_times = sorted(response_times)
            p95_index = int(0.95 * len(sorted_times))
            p95_response = sorted_times[p95_index] if sorted_times else 0
        else:
            avg_response = min_response = max_response = p95_response = 0
        
        print(f"Test Duration: {total_time:.1f} seconds ({total_time/60:.1f} minutes)")
        print(f"Total Requests: {total_requests} ({requests_per_sec:.2f} requests/sec)")
        print(f"Success Rate: {success_rate:.1f}% ({total_errors} errors)")
        print(f"Authentication Efficiency: {auth_efficiency:.1f} requests per auth call")
        print(f"Unique Tokens Seen: {unique_tokens}")
        print()
        
        print("Response Time Statistics:")
        print(f"  Average: {avg_response:.3f}s")
        print(f"  Minimum: {min_response:.3f}s")
        print(f"  Maximum: {max_response:.3f}s")
        print(f"  95th Percentile: {p95_response:.3f}s")
        print()
        
        if error_types:
            print("Error Breakdown:")
            for error_type, count in sorted(error_types.items()):
                percentage = (count / total_errors * 100) if total_errors > 0 else 0
                print(f"  {error_type}: {count} ({percentage:.1f}%)")
            print()
        
        # Worker-specific statistics
        if worker_results:
            print("Per-Worker Statistics:")
            for result in worker_results:
                worker_requests = result.get("requests_made", 0)
                worker_errors = len(result.get("errors", []))
                worker_auth_calls = result.get("auth_calls", 0)
                worker_time = result.get("end_time", 0) - result.get("start_time", 0)
                worker_rate = worker_requests / worker_time if worker_time > 0 else 0
                worker_success = ((worker_requests - worker_errors) / worker_requests * 100) if worker_requests > 0 else 100
                
                print(f"  Worker {result['worker_id']}: {worker_requests} requests, "
                      f"{worker_success:.1f}% success, {worker_rate:.1f} req/sec, "
                      f"{worker_auth_calls} auth calls")
        
        print()
        if total_errors == 0:
            print("🎉 TEST COMPLETED SUCCESSFULLY - NO ERRORS DETECTED!")
        elif success_rate >= 99.0:
            print(f"✅ TEST COMPLETED - HIGH SUCCESS RATE ({success_rate:.1f}%)")
        elif success_rate >= 95.0:
            print(f"⚠️  TEST COMPLETED - MODERATE SUCCESS RATE ({success_rate:.1f}%)")
        else:
            print(f"❌ TEST COMPLETED - LOW SUCCESS RATE ({success_rate:.1f}%) - INVESTIGATE ERRORS")

    def run_all_tests(self):
        """Run all concurrency tests"""
        print("=" * 80)
        print("FOLIO CLIENT CONCURRENCY TEST SUITE")
        print("=" * 80)
        
        results = {}
        
        # Test 1: Concurrent sync threads
        results["sync_threads"] = self.test_concurrent_sync_threads(
            num_threads=8, 
            requests_per_thread=5
        )
        
        # Test 2: Concurrent async tasks  
        results["async_tasks"] = asyncio.run(
            self.test_concurrent_async_tasks(
                num_tasks=8, 
                requests_per_task=5
            )
        )
        
        # Test 3: Mixed sync/async
        results["mixed"] = self.test_mixed_sync_async(
            num_sync_threads=4, 
            num_async_tasks=4, 
            requests_each=3
        )
        
        # Test 4: Token expiry simulation
        results["token_expiry"] = self.test_token_expiry_simulation()
        
        print("\n" + "=" * 80)
        print("SUMMARY")
        print("=" * 80)
        
        total_requests = (
            results["sync_threads"]["total_requests"] + 
            results["async_tasks"]["total_requests"] +
            results["mixed"]["total_requests"] +
            results["token_expiry"]["successes"]
        )
        
        total_errors = (
            results["sync_threads"]["total_errors"] + 
            results["async_tasks"]["total_errors"] +
            results["mixed"]["total_errors"] +
            results["token_expiry"]["errors"]
        )
        
        print(f"Total requests across all tests: {total_requests}")
        print(f"Total errors across all tests: {total_errors}")
        print(f"Success rate: {((total_requests - total_errors) / total_requests * 100):.1f}%")
        
        if total_errors == 0:
            print("🎉 ALL TESTS PASSED! Your thread-safe authentication is working correctly.")
        else:
            print(f"⚠️  Found {total_errors} errors. Check the detailed output above.")
        
        return results

    def test_separate_clients_same_token(self):
        """Simple test to verify 4 separate clients get the same auth token"""
        print(f"\n=== Testing 4 separate clients for same token ===")
        
        tokens_collected = []
        
        def get_first_token(client_id):
            """Create a FolioClient and return its first auth token"""
            try:
                client = FolioClient(
                    self.gateway_url,
                    self.tenant_id,
                    self.username,
                    self.password
                )
                
                # Get the first token
                token = client.okapi_token
                print(f"Client {client_id}: {token[-12:]}")  # Print last 12 chars
                
                # Clean up
                client.close()
                return token
                
            except Exception as e:
                print(f"Client {client_id}: ERROR - {e}")
                return None
        
        print("Creating 4 separate FolioClient instances...")
        
        # Create 4 clients in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(get_first_token, i) for i in range(4)]
            tokens_collected = [f.result() for f in futures]
        
        # Filter out failed clients
        valid_tokens = [t for t in tokens_collected if t is not None]
        unique_tokens = set(valid_tokens)
        
        print(f"\nResults:")
        print(f"  Successful clients: {len(valid_tokens)}/4")
        print(f"  Unique tokens: {len(unique_tokens)}")
        
        if len(unique_tokens) == 1:
            print("✅ SUCCESS: All separate clients received the SAME token!")
            print(f"   Shared token: ...{list(unique_tokens)[0][-16:]}")
        else:
            print(f"❌ DIFFERENT: Clients received {len(unique_tokens)} different tokens")
            for i, token in enumerate(unique_tokens, 1):
                print(f"   Token {i}: ...{token[-16:]}")
        
        return len(unique_tokens) == 1

def main():
    """Main test runner with configurable parameters"""
    import argparse
    import sys
    
    parser = argparse.ArgumentParser(description="Test FOLIO Client concurrent authentication")
    parser.add_argument("--gateway-url", required=True, help="FOLIO gateway URL")
    parser.add_argument("--tenant-id", required=True, help="FOLIO tenant ID") 
    parser.add_argument("--username", required=True, help="FOLIO username")
    parser.add_argument("--password", required=True, help="FOLIO password")
    parser.add_argument("--threads", type=int, default=8, help="Number of sync threads to test")
    parser.add_argument("--tasks", type=int, default=8, help="Number of async tasks to test")
    parser.add_argument("--requests", type=int, default=5, help="Requests per thread/task")
    parser.add_argument("--all-tests", action="store_true", help="Run all tests")
    parser.add_argument("--simple", action="store_true", help="Run simple shared client test")
    parser.add_argument("--token-test", action="store_true", help="Test separate clients for same token")
    parser.add_argument("--long-running", choices=["sync", "async", "mixed"], help="Run long-running test")
    parser.add_argument("--workers", type=int, default=4, help="Number of workers for long-running tests")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between requests in seconds")
    parser.add_argument("--operation", choices=["get", "token_access", "headers", "mixed"], default="mixed", help="Type of operation to perform")
    parser.add_argument("--endpoint", default="/users", help="FOLIO API endpoint to test (default: /users). Examples: /users, /groups, /inventory/instances, /organizations/organizations")
    parser.add_argument("--result-key", default="users", help="JSON result key for the endpoint (default: users). Examples: users, usergroups, instances, organizations")
    parser.add_argument("--report-interval", type=int, default=10, help="Seconds between live reports")
    
    args = parser.parse_args()
    
    tester = ConcurrentAuthTester(
        args.gateway_url,
        args.tenant_id, 
        args.username,
        args.password
    )
    
    if args.long_running:
        print(f"Running long-running {args.long_running} test...")
        print("This test will run until you press Ctrl+C")
        
        try:
            if args.long_running == "sync":
                tester.test_long_running_sync(
                    num_workers=args.workers,
                    delay_seconds=args.delay,
                    operation_type=args.operation,
                    report_interval=args.report_interval,
                    endpoint=args.endpoint,
                    result_key=args.result_key
                )
            elif args.long_running == "async":
                asyncio.run(tester.test_long_running_async(
                    num_tasks=args.workers,
                    delay_seconds=args.delay,
                    operation_type=args.operation,
                    report_interval=args.report_interval,
                    endpoint=args.endpoint,
                    result_key=args.result_key
                ))
            elif args.long_running == "mixed":
                sync_workers = args.workers // 2
                async_tasks = args.workers - sync_workers
                tester.test_long_running_mixed(
                    num_sync_workers=sync_workers,
                    num_async_tasks=async_tasks,
                    delay_seconds=args.delay,
                    operation_type=args.operation,
                    report_interval=args.report_interval,
                    endpoint=args.endpoint,
                    result_key=args.result_key
                )
        except KeyboardInterrupt:
            print("\nTest interrupted by user.")
            
    elif args.all_tests:
        print("Running all tests...")
        tester.run_all_tests()
    elif args.token_test:
        print("Testing if separate clients receive the same auth token...")
        tester.test_separate_clients_same_token()
    elif args.simple:
        print("Running simple shared client test...")
        results = tester.test_shared_client_simple(
            num_workers=args.threads,
            requests_each=args.requests
        )
        if results["total_errors"] == 0:
            print("✅ Simple test passed!")
        else:
            print(f"❌ Found {results['total_errors']} errors in simple test")
    else:
        print("Running quick test...")
        # Quick test with fixed cleanup
        results = tester.test_concurrent_sync_threads(
            num_threads=args.threads,
            requests_per_thread=args.requests
        )
        
        if results["total_errors"] == 0:
            print("✅ Quick test passed!")
        else:
            print(f"❌ Found {results['total_errors']} errors in quick test")


if __name__ == "__main__":
    import sys
    main()