(function () {
  "use strict";

  const databaseName = "enpiro";
  const databaseVersion = 2;
  const storeName = "environmental-observations";
  const preferenceStoreName = "preferences";

  function openDatabase() {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open(databaseName, databaseVersion);
      request.addEventListener("upgradeneeded", () => {
        const database = request.result;
        if (!database.objectStoreNames.contains(storeName)) {
          const store = database.createObjectStore(storeName, { keyPath: "recorded_at" });
          store.createIndex("observed_ms", "observed_ms");
        }
        if (!database.objectStoreNames.contains(preferenceStoreName)) {
          database.createObjectStore(preferenceStoreName, { keyPath: "key" });
        }
      });
      request.addEventListener("success", () => resolve(request.result));
      request.addEventListener("error", () => reject(request.error));
    });
  }

  async function withStore(mode, operation, selectedStoreName = storeName) {
    const database = await openDatabase();
    return new Promise((resolve, reject) => {
      const transaction = database.transaction(selectedStoreName, mode);
      const store = transaction.objectStore(selectedStoreName);
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

  function withoutObservedMs(records) {
    return records.map(({ observed_ms: _observedMs, ...reading }) => reading);
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
    return withoutObservedMs(records);
  }

  async function getRange(startMs, endMs) {
    const records = await withStore(
      "readonly",
      store => {
        const index = store.index("observed_ms");
        const hasStart = Number.isFinite(startMs);
        const hasEnd = Number.isFinite(endMs);
        if (hasStart && hasEnd) {
          return index.getAll(IDBKeyRange.bound(startMs, endMs));
        }
        if (hasStart) return index.getAll(IDBKeyRange.lowerBound(startMs));
        if (hasEnd) return index.getAll(IDBKeyRange.upperBound(endMs));
        return index.getAll();
      },
    );
    return withoutObservedMs(records);
  }

  async function clear() {
    await withStore("readwrite", store => store.clear());
  }

  async function getPreference(key) {
    const record = await withStore(
      "readonly",
      store => store.get(key),
      preferenceStoreName,
    );
    return record?.value;
  }

  async function putPreference(key, value) {
    await withStore(
      "readwrite",
      store => store.put({ key, value }),
      preferenceStoreName,
    );
  }

  window.EnpiroDataCache = {
    getAll,
    getRange,
    putMany,
    deleteMany,
    clear,
    getPreference,
    putPreference,
  };
}());
