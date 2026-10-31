import assert from 'node:assert/strict';
import { Common, Hardfork, Sepolia } from '@ethereumjs/common';
import { createEVM } from '@ethereumjs/evm';
import { Account, bytesToHex, createAddressFromString, hexToBytes } from '@ethereumjs/util';
import { Interface, zeroPadValue, toBeHex } from 'ethers';
import { compile, artifacts } from '../tools/compile.mjs';

export const BUILT = artifacts(compile({ support: true }));
export const A = '0x00000000000000000000000000000000000000a1';
export const B = '0x00000000000000000000000000000000000000b2';
export const C = '0x00000000000000000000000000000000000000c3';
export const X = '0x00000000000000000000000000000000000000d4';
export const Z = '0x0000000000000000000000000000000000000000';
export const word = n => zeroPadValue(toBeHex(n),32);

export class MemoryEVM {
  static async create() {
    // No provider, chain RPC, transaction package or signing keys. These are
    // direct message calls against ephemeral local state, not Sepolia execution.
    const instance = new MemoryEVM();
    instance.evm = await createEVM({ common: new Common({ chain: Sepolia, hardfork: Hardfork.Cancun }) });
    instance.calls = 0;
    for (const address of [A,B,C,X]) {
      await instance.evm.stateManager.putAccount(createAddressFromString(address), new Account(0n,10n**25n));
    }
    return instance;
  }

  async construct(name, args = []) {
    const iface = new Interface(BUILT[name].abi);
    const initcode = `0x${BUILT[name].evm.bytecode.object}${iface.encodeDeploy(args).slice(2)}`;
    const result = await this.evm.runCall({ caller:createAddressFromString(A), data:hexToBytes(initcode), gasLimit:20_000_000n });
    assert.equal(result.execResult.exceptionError, undefined, `${name} constructor: ${result.execResult.exceptionError?.error}`);
    assert.ok(result.createdAddress);
    return { name, address:result.createdAddress.toString(), iface };
  }

  async attempt(contract, fn, args = [], caller = A) {
    this.calls++;
    const data = contract.iface.encodeFunctionData(fn,args);
    const result = await this.evm.runCall({ caller:createAddressFromString(caller), to:createAddressFromString(contract.address),
      data:hexToBytes(data), gasLimit:20_000_000n, isStatic:contract.iface.getFunction(fn).stateMutability === 'view' });
    return result.execResult;
  }

  async call(contract, fn, args = [], caller = A) {
    const result = await this.attempt(contract,fn,args,caller);
    assert.equal(result.exceptionError, undefined, `${contract.name}.${fn}: ${result.exceptionError?.error}; ${bytesToHex(result.returnValue)}`);
    return contract.iface.decodeFunctionResult(fn,bytesToHex(result.returnValue));
  }

  async rejects(contract, fn, args, caller, errorName) {
    const result = await this.attempt(contract,fn,args,caller);
    assert.ok(result.exceptionError, `${fn} unexpectedly succeeded`);
    if (errorName) {
      const parsed = contract.iface.parseError(bytesToHex(result.returnValue));
      assert.equal(parsed?.name,errorName, `${fn}: ${bytesToHex(result.returnValue)}`);
    }
  }

  async setup({ registry = 'NodeRegistry', transit = 'TransitPolicy', connection = 'ConnectionPolicy' } = {}) {
    this.registry = await this.construct(registry);
    this.transit = await this.construct(transit,[this.registry.address]);
    this.connection = await this.construct(connection,[this.registry.address,this.transit.address]);
    for (const [i,owner] of [[1,A],[2,B],[3,C]]) {
      assert.equal((await this.call(this.registry,'register',[word(i*2),word(i*2+1),i === 3 ? 2 : 1],owner))[0],BigInt(i));
    }
    return this;
  }

  async edge(source = 1, destination = 3, salt = word(1), caller = A, { cost = 1, size = 1500, mask = 7 } = {}) {
    const rule = (await this.call(this.transit,'propose',[source,destination,salt,cost,size,mask],caller))[0];
    return rule;
  }

  async accept(contract, rule) {
    const fn = contract === this.transit ? 'edge' : 'connection';
    const data = await this.call(contract,fn,[rule]);
    for (const nft of [data[0],data[1]]) {
      const owner = (await this.call(this.registry,'ownerOf',[nft]))[0];
      await this.call(contract,'consent',[rule,data[2],nft],owner.toLowerCase());
    }
  }

  async connected() {
    const ar = await this.edge(1,3,word(1),A); await this.accept(this.transit,ar);
    const rb = await this.edge(3,2,word(2),C); await this.accept(this.transit,rb);
    const rule = (await this.call(this.connection,'propose',[1,2,word(9),1,7,1500,[ar,rb].sort()],A))[0];
    await this.accept(this.connection,rule);
    return { ar,rb,rule };
  }
}
