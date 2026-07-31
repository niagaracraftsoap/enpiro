(function () {
  "use strict";

  const databaseName = "enpiro";
  const databaseVersion = 1;
  const storeName = "environmental-observations";

  function openDatabase() {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open(databaseName, databaseVersion);
      request.addEventListener("upgradeneeded", () => {
        const database = request.result;
        if (!database.objectStoreNames.contains(storeName)) {
          const store = database.createObjectStore(storeName, { keyPath: "recorded_at" });
          store.createIndex("observed_ms", "observed_ms");
        }
      });
      request.addEventListener("success", () => resolve(request.result));
      request.addEventListener("error", () => reject(request.error));
    });
  }

  async function withStore(mode, operation) {
    const database = await openDatabase();
    return new Promise((resolve, reject) => {
      const transaction = database.transaction(storeName, mode);
      const store = transaction.objectStore(storeName);
      let result;
      transaction.addEventListener("complete", () => {
        database.close();
        resolve(result instanceof IDBRequest ? result.result : result);
      });
      transaction.addEventListener("abort", () => {
        database.close();
        reject(transaction.error);
      });
      transaction.addEventListener("error", () => reject(transaction.error));
      result = operation(store);
    });
  }

  function normalized(reading) {
    const observedMs = new Date(reading.recorded_at).getTime();
    if (!Number.isFinite(observedMs)) throw new Error("Invalid observation timestamp");
    return { ...reading, observed_ms: observedMs };
  }

  async function putMany(readings) {
    if (!readings.length) return;
    await withStore("readwrite", store => {
      readings.forEach(reading => store.put(normalized(reading)));
    });
  }

  async function deleteMany(recordedTimes) {
    if (!recordedTimes.length) return;
    await withStore("readwrite", store => {
      recordedTimes.forEach(recordedAt => store.delete(recordedAt));
    });
  }

  async function getAll() {
    const records = await withStore(
      "readonly",
      store => store.index("observed_ms").getAll(),
    );
    return records.map(({ observed_ms: _observedMs, ...reading }) => reading);
  }

  async function clear() {
    await withStore("readwrite", store => store.clear());
  }

  window.EnpiroDataCache = { getAll, putMany, deleteMany, clear };
}());
