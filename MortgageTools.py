import pandas as pd
import numpy as np
import sys
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def get_loan_id_from_row(row: pd.DataFrame):
    '''
    Utility function to get the loan_id from the key of a row dataframe
    '''
    return row['key'][0]
def get_date_from_row(row: pd.DataFrame):
    '''
    Utility function to get the date from the key of a row dataframe
    '''
    return row['key'][1]

def load_data( full_file_name:str, sheet_names:tuple):
    '''
    Load the data from the excel file and merge all tge sheets into the first sheet.
    '''
    
    # First get the Variable data (Non Static) and combine it into a DataFrame keyed on Loan_id and Month
    combined_variable_df=pd.DataFrame()
    for add_sheet in sheet_names[1:]:
        add_df=pd.read_excel(open(full_file_name,'rb'), add_sheet)

        # Sanitise data by converting to lower case
        add_df.columns = [str(x).lower() for x in add_df.columns]
        add_df.fillna(np.nan)
        
        #Check if loan_id is one of the columns
        if "loan_id" not in add_df.columns.values:
            return(f'Cannot find loan_id in {add_sheet}')
        
        suffix=add_sheet[5:].replace(" ","_")
        
        new_data={}
        for index,row in add_df.iterrows():
            loan_id=int(add_df.loc[index].at['loan_id'])
            for col in add_df.columns[1:]:
                col_name=col.split(" ")[0]
                if add_df.loc[index].at[col] >= 0:
                    key=(loan_id,datetime.strptime(col_name,'%Y-%m-%d'))
                    new_data[key]= add_df.loc[index].at[col]
        
        new_df=pd.DataFrame(new_data.items(), columns=['key', suffix])
        
        if combined_variable_df.empty:
            combined_variable_df=new_df
        else:
            combined_variable_df=pd.merge(combined_variable_df,new_df,left_on="key", right_on="key")
        
        #Sanity check that we are not missing any loans (Outer join row check perhaps)
        if len(new_df)!=len(combined_variable_df):
            logger.warning(f'Failed to match up all loans in DATA tables \n{add_sheet} has {len(new_df)} rows\nPrevious sheets have {len(combined_variable_df)}')
        
    # Add the loan_id back in again.
    combined_variable_df['loan_id']=combined_variable_df.apply(get_loan_id_from_row, axis=1)
    combined_variable_df['valuation_date']=combined_variable_df.apply(get_date_from_row, axis=1)

    
    #Then get the static data    
    static_df=pd.read_excel(open(full_file_name,'rb'), sheet_names[0], skiprows=[0,1])
    
    # Sanitise data by converting to lower case
    static_df.columns = [x.lower() for x in static_df.columns]
    
    # Check that loan_id is one of the columns
    if "loan_id" not in static_df.columns.values:
        return(f'Cannot find loan_id in {sheet_names[0]}')

    
    #Finally merge the combined dynamic data  with the Static Data
    final_df=pd.merge(combined_variable_df,static_df,left_on="loan_id", right_on="loan_id")
    
    # return the results
    return final_df

def _print_loan_no(loan_id: str, raw_data: pd.DataFrame, start: str, end: str):
    '''
    Utility function to print out the detauls of one loan_id between set dates
    '''
    start=datetime.strptime(start,'%Y-%m-%d')
    end=datetime.strptime(end,'%Y-%m-%d')
    
    logger.info("LOANID","DATE","Month_End_Balances","Payment_Made",
          "seasoning","n_missed_payments","prepaid_in_month",
          "default_in_month","recovery_in_month","is_recovery_payment",
          "time_to_reversion","is_post_seller_purchase_date",
          "postdefault_recoveries","prepayment_date",
          "date_of_default","date_of_recovery",
          "exposure_at_default","recovery_percent")
    for index,row in raw_data.iterrows():
        if row['loan_id']==loan_id:
            if row['key'][1]>=start and row['key'][1]<=end:
                logger.info(loan_id, row['key'][1],row['Month_End_Balances'],row['Payment_Made'],
                      row['seasoning'],row['n_missed_payments'],row['prepaid_in_month'],
                      row['default_in_month'],row['recovery_in_month'],row['is_recovery_payment'],
                      row['time_to_reversion'], row['is_post_seller_purchase_date'],
                      row['postdefault_recoveries'], row['prepayment_date'],
                      row['date_of_default'], row['date_of_recovery'],
                      row['exposure_at_default'],row['recovery_percent'])
            #else:
    
def _diff_month(date1: datetime, date2: datetime):
    return (date1.year - date2.year) * 12 + date1.month - date2.month

def _calculate_current_balance(row: pd.DataFrame):
    return(row['Month_End_Balances'])

def _calculate_seasoning(row: pd.DataFrame):
    return(_diff_month(row['key'][1],row['origination_date']))

def _calculate_delinquency(raw_data: pd.DataFrame): #Missed payments in a row
    raw_data.insert(15,'n_missed_payments',0)
    for i in range(2,len(raw_data)):
        if raw_data.loc[i].at["Payment_Made"]==0 and raw_data.loc[i].at["Payment_Due"]!=0:
            loan_id=raw_data.loc[i].at['loan_id']
            key=raw_data.loc[i].at['key']
            previous_missed=raw_data.loc[i-1].at["n_missed_payments"]
            raw_data.loc[i,'n_missed_payments']=raw_data.loc[i-1,'n_missed_payments']+1
            missed=raw_data.loc[i].at['n_missed_payments']

def _calculate_prepaid(row: pd.DataFrame):
    prepaid=False
    if int(row['Month_End_Balances'])==0 and int(row['Payment_Made'])>0 and int(row['Payment_Due'])>0:
        prepaid=True
    return(prepaid)

def _calculate_defaults(row: pd.DataFrame):
    defaults=False
    if int(row['n_missed_payments'])==3:
        defaults=True
    return defaults

def _calculate_month_since_default(row: pd.DataFrame):
    months_since_default=_diff_month(row['valuation_date'],row['date_of_default'])
    # If it is before default then this will be negative.
    return months_since_default

def _calculate_default_vintage(row: pd.DataFrame):
    default_vintage=row['date_of_default'].year
    if default_vintage>0:
        return default_vintage
    else:
        return 0
    
def _calculate_recoveries(row: pd.DataFrame):
    is_recovery=False
    if row['date_of_default'] and row['date_of_default']<=row['valuation_date'] and int(row['Payment_Made'])>0:
        is_recovery=True
    return(is_recovery)

def _calculate_is_recovery(row: pd.DataFrame):
    is_recovery=False
        
    if row['date_of_default'] and row['date_of_default']<=row['valuation_date'] and int(row['Payment_Made'])>0:
        is_recovery=True
    return(is_recovery)

def _calculate_reversions(row: pd.DataFrame):
    return(_diff_month(row['key'][1],row['reversion_date']))

def _calculate_post_seller_purchase_date(row: pd.DataFrame):
    post_seller=False
    if _diff_month(row['key'][1],row['investor_1_acquisition_date'])>0:
        post_seller=True
    return post_seller

def _calculate_static(raw_data: pd.DataFrame):
    '''
    Utility function to enhance the data by calculating static information per loan
    Once done, "outer join" the static data back to the input data
    '''
    static={}

    for i in range(2,len(raw_data)):
        loan_id=raw_data.loc[i].at['loan_id']
        key=raw_data.loc[i].at['key']
        if loan_id not in static.keys():
            static[loan_id]={}
            static[loan_id]['loan_id']=loan_id
            static[loan_id]['postdefault_recoveries']=0
            static[loan_id]['exposure_at_default']=0
            static[loan_id]['date_of_recovery']=None
            static[loan_id]['prepayment_date']=None
            static[loan_id]['date_of_default']=None
        
        if raw_data.loc[i].at['default_in_month']:
            static[loan_id]['date_of_default']=key[1]
            static[loan_id]['exposure_at_default']=raw_data.loc[i].at["Month_End_Balances"]
        else:
            if 'date_of_default' in static[loan_id] and static[loan_id]['date_of_default'] and raw_data.loc[i].at["valuation_date"]>static[loan_id]['date_of_default']:
                static[loan_id]['postdefault_recoveries']+=raw_data.loc[i].at['Payment_Made']
                    
        if raw_data.loc[i].at["prepaid_in_month"]:
            static[loan_id]['prepayment_date']=key[1]
            
        if static[loan_id]["date_of_default"] and static[loan_id]["date_of_default"]<=key[1]:
            static[loan_id]['date_of_recovery']=key[1]
            
    for loan_id in static.keys():
        if static[loan_id]['exposure_at_default']==0:
            static[loan_id]['recovery_percent']=0
        else:
            static[loan_id]['recovery_percent']=static[loan_id]['postdefault_recoveries']/static[loan_id]['exposure_at_default']

     
    # Now merge the staic data with the dataframe
    static_df=pd.DataFrame(static).transpose()
    final_df=pd.merge(raw_data,static_df,how="left",left_on="loan_id", right_on="loan_id")
    return(final_df)
        
def enhance_data(raw_data: pd.DataFrame):
    '''
    Enhance the input data by adding derived columns
    '''
    #Add current_balance
    # This is just Month_End_Balances - query on this
    raw_data['current_balance']=raw_data.apply(_calculate_current_balance, axis=1)
    logger.debug(f'Raw_data10 {raw_data.shape}')

    #Add seasoning:
    raw_data['seasoning']=raw_data.apply(_calculate_seasoning, axis=1)
    logger.debug(f'Raw_data9 {raw_data.shape}')
    
    #Add n_missed_payments (Delinquency)
    _calculate_delinquency(raw_data)
    logger.debug(f'Raw_data8 {raw_data.shape}')
    
    #Add prepaid_in_month
    raw_data['prepaid_in_month']=raw_data.apply(_calculate_prepaid, axis=1)
    logger.debug(f'Raw_data7 {raw_data.shape}')
    
    #Add default_in_month
    raw_data['default_in_month']=raw_data.apply(_calculate_defaults, axis=1)
    logger.debug(f'Raw_data6 {raw_data.shape}')
    
    #Add time_to_reversion
    raw_data['time_to_reversion']=raw_data.apply(_calculate_reversions, axis=1)
    logger.debug(f'Raw_data4 {raw_data.shape}')
    
    #Add is_post_seller_purchase_date
    raw_data['is_post_seller_purchase_date']=raw_data.apply(_calculate_post_seller_purchase_date, axis=1)
    logger.debug(f'Raw_data3 {raw_data.shape}')

    # Add postdefault_recoveries
    raw_data=_calculate_static(raw_data)
    logger.debug(f'Raw_data2 {raw_data.shape}')
    
    
    #Add is_recovery_payment - the text here is unclear - it appears to be the same logic as recovery_in_month
    raw_data['is_recovery_payment']=raw_data.apply(_calculate_is_recovery, axis=1)
    logger.debug(f'Raw_data5 {raw_data.shape}')
   
    #Add recovery_in_month
    raw_data['recovery_in_month']=raw_data.apply(_calculate_recoveries, axis=1)
    test=raw_data[raw_data['loan_id']==3][['loan_id','valuation_date','Payment_Made','recovery_in_month','date_of_default']]
    logger.debug(f'Raw_data1 {test}')
    logger.debug(f'Raw_data1 {raw_data.shape}')

    #Add months since default
    raw_data['months_since_default']=raw_data.apply(_calculate_month_since_default, axis=1)

    #Add default_vintage
    raw_data['default_vintage']=raw_data.apply(_calculate_default_vintage, axis=1)
    logger.debug(f'Raw_data1 {raw_data.shape}')

    return(raw_data)

def load_and_enhance_data(full_file_name: str, sheet_names: tuple):
    '''
    Simplify the user experience by calling load and enhance together
    '''
    results=load_data(full_file_name,sheet_names)
    enhanced=enhance_data(results)
    return enhanced


def get_CPR(raw_data: pd.DataFrame, pivot_columns: list=['seasoning']):
    '''
    Calculate the CPR based on a set of pivot_columns
    '''
    return_dict={}
    for pivot_column in pivot_columns:
        for key in raw_data[pivot_column]:
            subset_df=raw_data.loc[raw_data[pivot_column] == key]
            subset_plus1_df=raw_data.loc[raw_data[pivot_column] == key+1]

            prepaid=subset_plus1_df[subset_plus1_df['prepaid_in_month']==True]['Payment_Made'].sum()
            balance=subset_df[(subset_df['prepaid_in_month']==False) & (subset_df['default_in_month']==False)]['Month_End_Balances'].sum()
            
            # On the off chance that there is no key+1 row, then its sum should be 0 anyway.
            if len(subset_plus1_df)==0:
                prepaid=0

            CPR=1-pow(1-prepaid/balance,12)
            if key in return_dict:
                return_dict[key][pivot_column] = CPR
            else:
                return_dict[key] = {pivot_column : CPR}
            
    return_df=pd.DataFrame(return_dict).transpose()
    return return_df
        
def get_CDR(raw_data: pd.DataFrame, pivot_columns: list=['seasoning']):
    '''
    Calculate the CDR based on a set of pivot_columns
    '''
    return_dict={}
    for pivot_column in pivot_columns:
        for key in raw_data[pivot_column]:
            subset_df=raw_data.loc[raw_data[pivot_column] == key]
            subset_plus1_df=raw_data.loc[raw_data[pivot_column] == key+1]

            defaulted=subset_plus1_df[subset_plus1_df['default_in_month']==True]['Month_End_Balances'].sum()
            balance=subset_df[(subset_df['prepaid_in_month']==False) & (subset_df['default_in_month']==False)]['Month_End_Balances'].sum()
            CDR=1-pow(1-defaulted/balance,12)
            
            # On the off chance that there is no key+1 row, then its sum should be 0 anyway.
            if len(subset_plus1_df)==0:
                defaulted=0

            if key in return_dict:
                return_dict[key][pivot_column] = CDR
            else:
                return_dict[key] = {pivot_column : CDR}
    return_df=pd.DataFrame(return_dict).transpose()
    return return_df

def get_recoveries(raw_data: pd.DataFrame):
    '''
    Calculate the recoveries based on the months_since_default
    '''
    pivot_column='months_since_default'
    return_dict={}
    for key in raw_data[pivot_column]:
        subset_df=raw_data.loc[raw_data[pivot_column] == key]

        defaulted=subset_df[subset_df['months_since_default']>0]['postdefault_recoveries'].sum()
        exposure=subset_df[subset_df['months_since_default']>0]['current_balance'].sum()
        if exposure>0:
            recovery=defaulted/exposure
        else:
            recovery=0

        if key in return_dict:
            return_dict[key][pivot_column] = recovery
        else:
            return_dict[key] = {pivot_column : recovery}
    return_df=pd.DataFrame(return_dict).transpose()
    return_df=return_df.rename({'months_since_default': 'recoveries'}, axis=1)
    return_df=return_df.reset_index().rename(columns={"index":"months_since_default"})
    return_df = return_df.reset_index(drop=True)
    
    return return_df
 
def get_CPR_CDR_curves(raw_data: pd.DataFrame):
    '''
    Get the CPR and CDR curves and join them together
    '''
    return_dict={}
    for key in raw_data['product'].unique():
        subset_df=raw_data.loc[raw_data['product'] == key]

        CPR=get_CPR(raw_data, ['time_to_reversion'])
        CPR=CPR.rename({'time_to_reversion':'CPR'}, axis=1)

        CDR=get_CDR(raw_data, ['time_to_reversion'])
        CDR=CDR.rename({'time_to_reversion':'CDR'}, axis=1)

        CPR_CDR=pd.concat([CPR,CDR], axis="columns")

        return_dict[key] = CPR_CDR
    return return_dict

def get_recovery_curves(raw_data: pd.DataFrame):
    '''
    Get the recovery curves
    '''
    return_dict={}
    for key in raw_data['default_vintage'].unique():
        subset_df=raw_data.loc[raw_data['default_vintage'] == key]

        recovery_curves=get_recoveries(subset_df)

        return_dict[key] = recovery_curves
    return return_dict
 
def _calculate_probablity_of_recovery(row: pd.DataFrame, recovery_curves: dict):
    '''
    Utility function to get the recovery probability based on months since default
    '''
    recovery_probability = 0
    year=row['default_vintage']
    if year==0:
        #no default occurred in these - no point going further
        return recovery_probability

    loan_id=row['loan_id']
    valuation_date=row['valuation_date']
    months_since_default=row['months_since_default']
    rec_df=recovery_curves[year]
    rec_df=rec_df[rec_df['months_since_default']==months_since_default]
    if len(rec_df)==1:
        recovery_probability=rec_df.iloc[0,1]
    else:
        logger.warning(f'calculate_probablity_of_recovery: months_since_default({months_since_default}) '
              f'not in recovery_curves[{year}]={recovery_curves[year]}{type(recovery_curves[year])}')
    return(recovery_probability)


def _calculate_recovery_over_EAD(row: pd.DataFrame):
    '''
    Utility function to get the recovery over the Exposure at Default
    '''
    recovery_over_EAD = 0
    if row['exposure_at_default']>0:
        recovery_over_EAD=row['postdefault_recoveries']/row['exposure_at_default']
    return(recovery_over_EAD)

def decompose_recoveries(recovery_curves: dict, raw_data: pd.DataFrame):
    '''
    Decompose the recovery probability and revoery over EAD back into the raw data
    '''
    subset_df=raw_data.copy()

    subset_df['recovery_probability']=subset_df.apply(_calculate_probablity_of_recovery, recovery_curves=recovery_curves, axis=1)
    subset_df['recovery_over_EAD']=subset_df.apply(_calculate_recovery_over_EAD, axis=1)

    return subset_df

def _calculate_cashflows(row: pd.DataFrame, CPR_CDR: dict, recovery_curves: dict):
    '''
    Utility function to calculate the cashflows given CPR/CDR/recovery
    '''
    product=row['product']
    month=row['time_to_reversion']
    cpr=0
    cdr=0
    cpdr_df=CPR_CDR[product].reset_index()
    cpdr_df=cpdr_df[cpdr_df['index']==month]
    cpr=cpdr_df.iloc[0].at['CPR'] # /100
    cdr=cpdr_df.iloc[0].at['CDR'] # /100

    rec_curve=recovery_curves[row['default_vintage']]
    recovery=0
    months_since_default=row['months_since_default']
    payment_due=row['Payment_Due']
    if months_since_default>0:
        # It already defaulted so there is no prepayment, and no further chance of default and no expected payment
        recovery=rec_curve[rec_curve['months_since_default']==months_since_default].iloc[0].at['recoveries']/100
        cpr=0
        cdr=0
        payment_due=0
    if months_since_default==0:
        # It  defaulted today so CDR is 100%, there is no prepayment, no expected payment
        cdr=1
        cpr=0
        payment_due=0
    
    cashflow=payment_due+cpr*row['Month_End_Balances']-cdr*row['Month_End_Balances']+recovery*row['Month_End_Balances']
    return cashflow

def get_cashflows(data: pd.DataFrame, CPR_CDR: dict, recovery_curves: dict):
    ret_data=data.copy()
    ret_data['projected_cash_flow']=ret_data.apply(_calculate_cashflows, CPR_CDR=CPR_CDR, recovery_curves=recovery_curves, axis=1)
    return ret_data